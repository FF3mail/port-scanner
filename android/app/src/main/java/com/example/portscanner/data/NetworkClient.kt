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

class ServerUnreachableException : IOException("Server unreachable")

class UnauthorizedException : IOException("Unauthorized")

class ServerHttpException(
    val statusCode: Int,
    message: String,
) : IOException(message)

class NetworkClient {

    suspend fun postScan(ip: String, token: String, ports: List<Int>): ScanResult = withContext(Dispatchers.IO) {
        val connection = openPostConnection(ip)
        try {
            connection.setRequestProperty("Authorization", "Bearer $token")
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
            throw ServerUnreachableException()
        } catch (e: SocketTimeoutException) {
            throw ServerUnreachableException()
        } finally {
            connection.disconnect()
        }
    }

    suspend fun scanPorts(ip: String, ports: List<Int>): Map<Int, String> = withContext(Dispatchers.IO) {
        try {
            InetAddress.getByName(ip)
        } catch (e: UnknownHostException) {
            throw e
        }
        val results = LinkedHashMap<Int, String>()
        for (port in ports) {
            results[port] = scanSinglePort(ip, port)
        }
        results
    }

    private fun openPostConnection(ip: String): HttpURLConnection {
        val url = URL("http://$ip:8080/scan")
        val connection = url.openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = CONNECT_TIMEOUT_MS.toInt()
        connection.readTimeout = CONNECT_TIMEOUT_MS.toInt()
        return connection
    }

    private fun scanSinglePort(ip: String, port: Int): String {
        return try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress(ip, port), PORT_TIMEOUT_MS.toInt())
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
        const val CONNECT_TIMEOUT_MS = 3000L
        const val PORT_TIMEOUT_MS = 1500L
        const val MAX_PORTS = 30
    }
}
