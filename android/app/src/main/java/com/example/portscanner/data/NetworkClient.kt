package com.example.portscanner.data

import com.example.portscanner.domain.ScanResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.ConnectException
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.net.URL
import java.net.UnknownHostException
import java.security.MessageDigest
import javax.net.ssl.SSLException

class ServerUnreachableException : IOException("Server unreachable")

class UnauthorizedException : IOException("Unauthorized")

class ServerHttpException(
    val statusCode: Int,
    message: String,
) : IOException(message)

/**
 * Maps transport-layer failures during POST /scan to [ServerUnreachableException].
 * HTTP status errors (401/400/…) are handled separately and must not pass through here.
 */
internal fun mapPostScanTransportFailure(cause: IOException): IOException = when (cause) {
    is ConnectException, is SocketTimeoutException, is UnknownHostException, is SSLException ->
        ServerUnreachableException()
    else -> cause
}

class NetworkClient {

    suspend fun postScan(endpoint: ScanEndpoint, token: String, ports: List<Int>): ScanResult =
        withContext(Dispatchers.IO) {
            val connection = openPostConnection(endpoint)
            try {
                val bearerToken = generateTimeLimitedToken(token)
                connection.setRequestProperty("Authorization", "Bearer $bearerToken")
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.doOutput = true

                val requestJson = JSONObject().put("ports", JSONArray(ports))
                connection.outputStream.use { stream ->
                    val bytes = requestJson.toString().toByteArray(Charsets.UTF_8)
                    stream.write(bytes)
                }

                val statusCode = connection.responseCode
                when (statusCode) {
                    HttpURLConnection.HTTP_OK -> {
                        val body = connection.inputStream.bufferedReader().use { it.readText() }
                        ScanResult(parseResults(body, ports))
                    }
                    HttpURLConnection.HTTP_UNAUTHORIZED -> throw UnauthorizedException()
                    HttpURLConnection.HTTP_BAD_REQUEST,
                    HttpURLConnection.HTTP_INTERNAL_ERROR,
                    -> {
                        val errorMessage = readErrorMessage(connection)
                        throw ServerHttpException(statusCode, errorMessage)
                    }
                    else -> {
                        val errorMessage = readErrorMessage(connection)
                        throw ServerHttpException(statusCode, errorMessage)
                    }
                }
            } catch (e: ConnectException) {
                throw mapPostScanTransportFailure(e)
            } catch (e: SocketTimeoutException) {
                throw mapPostScanTransportFailure(e)
            } catch (e: UnknownHostException) {
                throw mapPostScanTransportFailure(e)
            } catch (e: SSLException) {
                throw mapPostScanTransportFailure(e)
            } finally {
                connection.disconnect()
            }
        }

    suspend fun scanPorts(endpoint: ScanEndpoint, ports: List<Int>): Map<Int, String> =
        withContext(Dispatchers.IO) {
            val socketHost = endpoint.socketHost()
            try {
                InetAddress.getByName(socketHost)
            } catch (e: UnknownHostException) {
                throw e
            }
            val results = LinkedHashMap<Int, String>()
            for (port in ports) {
                results[port] = scanSinglePort(socketHost, port)
            }
            results
        }

    private fun openPostConnection(endpoint: ScanEndpoint): HttpURLConnection {
        val url = URL(endpoint.scanUrlString())
        val connection = url.openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = CONNECT_TIMEOUT_MS.toInt()
        connection.readTimeout = HTTP_READ_TIMEOUT_MS.toInt()
        return connection
    }

    private fun scanSinglePort(host: String, port: Int): String {
        return try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress(host, port), PORT_TIMEOUT_MS.toInt())
                "OPEN"
            }
        } catch (_: IOException) {
            "CLOSED"
        }
    }

    private fun parseResults(body: String, ports: List<Int>): Map<Int, String> {
        val json = JSONObject(body)
        val resultsObject = json.getJSONObject("results")
        val map = LinkedHashMap<Int, String>()
        for (port in ports) {
            val key = port.toString()
            val status = if (resultsObject.has(key)) {
                resultsObject.getString(key)
            } else {
                "CLOSED"
            }
            map[port] = status
        }
        return map
    }

    private fun readErrorMessage(connection: HttpURLConnection): String {
        val stream = connection.errorStream ?: connection.inputStream
        if (stream == null) {
            return "HTTP ${connection.responseCode}"
        }
        val body = stream.bufferedReader().use { it.readText() }
        return try {
            JSONObject(body).optString("error", body)
        } catch (_: Exception) {
            body.ifBlank { "HTTP ${connection.responseCode}" }
        }
    }

    companion object {
        /** TCP connect budget for POST /scan (independent of server scan duration). */
        const val CONNECT_TIMEOUT_MS = 3000L

        /**
         * Per-port connect timeout for client-side socket scans (not the HTTP read timeout).
         */
        const val PORT_TIMEOUT_MS = 1500L

        const val MAX_PORTS = 30

        /**
         * Matches server `SCAN_TIMEOUT` (1.0 s) in `server/server.py` for worst-case scan math.
         */
        const val SERVER_SCAN_TIMEOUT_PER_PORT_MS = 1000L

        /**
         * Extra headroom beyond sequential server scan time (JSON, scheduling).
         * Does not guarantee success on every device, network, or OS scheduler.
         */
        const val HTTP_READ_SAFETY_MARGIN_MS = 5000L

        /**
         * HTTP response read timeout for POST /scan while the server scans up to [MAX_PORTS] ports.
         * Worst-case server work ≈ [MAX_PORTS] × [SERVER_SCAN_TIMEOUT_PER_PORT_MS].
         */
        const val HTTP_READ_TIMEOUT_MS =
            MAX_PORTS * SERVER_SCAN_TIMEOUT_PER_PORT_MS + HTTP_READ_SAFETY_MARGIN_MS
        const val TOKEN_VALIDITY_SECONDS = 6 * 3600L

        /**
         * Demo master secret documented in prompts/00_overview.md.
         * Not used for live scan requests — callers must pass the UI-entered secret.
         */
        const val DEMO_SECRET_TOKEN = "my_secret_123"

        /**
         * Тот же алгоритм, что на сервере: SHA-256(master_secret + ":" + window_id), lowercase hex.
         * window_id = floor(unix_seconds / TOKEN_VALIDITY_SECONDS).
         * Requires an explicit master secret (from UI); no hardcoded fallback for live scans.
         */
        fun generateTimeLimitedToken(
            masterSecret: String,
            unixSeconds: Long = System.currentTimeMillis() / 1000L,
        ): String {
            val windowId = unixSeconds / TOKEN_VALIDITY_SECONDS
            val payload = "$masterSecret:$windowId"
            val digest = MessageDigest.getInstance("SHA-256")
                .digest(payload.toByteArray(Charsets.UTF_8))
            return digest.joinToString("") { byte -> "%02x".format(byte) }
        }
    }
}
