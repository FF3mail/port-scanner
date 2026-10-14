package com.example.portscanner.domain

data class PortComparison(
    val port: Int,
    val serverStatus: PortStatus,
    val clientStatus: PortStatus,
) {
    val isMatch: Boolean
        get() = serverStatus == clientStatus

    fun formatLine(): String {
        val server = serverStatus.name
        val client = clientStatus.name
        val verdict = when {
            serverStatus == clientStatus -> "✅ Match OK"
            serverStatus == PortStatus.OPEN && clientStatus == PortStatus.CLOSED ->
                "⚠️ Заблокирован файрволом/NAT!"
            else -> "⚠️ Расхождение"
        }
        return "Порт $port: Сервер $server, Клиент $client → $verdict"
    }
}
