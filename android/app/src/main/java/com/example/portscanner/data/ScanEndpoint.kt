package com.example.portscanner.data

import java.net.InetAddress
import java.net.URI

/**
 * HTTPS target for `POST /scan` (TLS is terminated outside the Python server).
 */
data class ScanEndpoint(
    val host: String,
    val httpsPort: Int,
) {
    fun scanUrlString(): String = buildHttpsScanUrl(host, httpsPort)

    /** Host string suitable for TCP client-side checks (no URI brackets). */
    fun socketHost(): String = hostForUri(host)
}

object ScanEndpointParser {
    const val DEFAULT_HTTPS_PORT = 443

    sealed class Result {
        data class Ok(val endpoint: ScanEndpoint) : Result()
        data class Error(val message: String) : Result()
    }

    fun parse(hostInput: String, httpsPortInput: String): Result {
        val hostResult = parseHost(hostInput)
        if (hostResult is HostParse.Error) {
            return Result.Error(hostResult.message)
        }
        val host = (hostResult as HostParse.Ok).host

        val portResult = parseHttpsPort(httpsPortInput)
        if (portResult is PortParse.Error) {
            return Result.Error(portResult.message)
        }
        val port = (portResult as PortParse.Ok).port

        return Result.Ok(ScanEndpoint(host, port))
    }

    internal fun buildHttpsScanUrl(host: String, httpsPort: Int): String {
        val uriHost = hostForUri(host)
        val uri = URI("https", null, uriHost, httpsPort, "/scan", null, null)
        return uri.toASCIIString()
    }

    private sealed class HostParse {
        data class Ok(val host: String) : HostParse()
        data class Error(val message: String) : HostParse()
    }

    private sealed class PortParse {
        data class Ok(val port: Int) : PortParse()
        data class Error(val message: String) : PortParse()
    }

    private fun parseHost(raw: String): HostParse {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) {
            return HostParse.Error("Введите домен или IP сервера")
        }
        if (trimmed.any { it.isWhitespace() }) {
            return HostParse.Error("Некорректный адрес сервера")
        }
        val lower = trimmed.lowercase()
        if (lower.startsWith("http://") || lower.startsWith("https://")) {
            return HostParse.Error("Укажите только домен или IP, без http:// или https://")
        }
        if (trimmed.contains("://") || trimmed.contains('@') ||
            trimmed.contains('/') || trimmed.contains('?') || trimmed.contains('#')
        ) {
            return HostParse.Error("Некорректный адрес сервера")
        }

        val host = when {
            trimmed.startsWith("[") && trimmed.endsWith("]") -> {
                val inner = trimmed.substring(1, trimmed.length - 1)
                if (inner.isEmpty() || !isIpLiteral(inner)) {
                    return HostParse.Error("Некорректный IPv6-адрес")
                }
                trimmed
            }
            isIpv4Literal(trimmed) || isUnbracketedIpv6Literal(trimmed) -> trimmed
            isDomainName(trimmed) -> trimmed
            else -> return HostParse.Error("Некорректный адрес сервера")
        }
        return HostParse.Ok(host)
    }

    private fun parseHttpsPort(raw: String): PortParse {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) {
            return PortParse.Ok(DEFAULT_HTTPS_PORT)
        }
        val port = trimmed.toIntOrNull()
            ?: return PortParse.Error("Некорректный HTTPS-порт")
        if (port !in 1..65535) {
            return PortParse.Error("HTTPS-порт должен быть от 1 до 65535")
        }
        return PortParse.Ok(port)
    }

    internal fun hostForUri(host: String): String {
        if (host.startsWith("[") && host.endsWith("]")) {
            return host.substring(1, host.length - 1)
        }
        return host
    }

    private fun isIpv4Literal(host: String): Boolean {
        val parts = host.split('.')
        if (parts.size != 4) {
            return false
        }
        for (part in parts) {
            val value = part.toIntOrNull() ?: return false
            if (value !in 0..255) {
                return false
            }
        }
        return true
    }

    private fun isUnbracketedIpv6Literal(host: String): Boolean {
        if (!host.contains(':')) {
            return false
        }
        return isIpLiteral(host)
    }

    private fun isIpLiteral(host: String): Boolean {
        return try {
            val address = InetAddress.getByName(host)
            val canonical = address.hostAddress ?: return false
            canonical == host || canonical.contains(':') && host.contains(':')
        } catch (_: Exception) {
            false
        }
    }

    private fun isDomainName(host: String): Boolean {
        if (host.length > 253 || host.startsWith('.') || host.endsWith('.')) {
            return false
        }
        if (host.contains("..")) {
            return false
        }
        val labels = host.split('.')
        if (labels.isEmpty()) {
            return false
        }
        for (label in labels) {
            if (label.isEmpty() || label.length > 63) {
                return false
            }
            if (!label.all { it.isLetterOrDigit() || it == '-' }) {
                return false
            }
            if (label.startsWith('-') || label.endsWith('-')) {
                return false
            }
        }
        return true
    }
}
