package com.example.portscanner.domain

enum class PortStatus {
    OPEN,
    CLOSED,
    ;

    companion object {
        fun fromRaw(value: String?): PortStatus {
            return when (value?.uppercase()) {
                "OPEN" -> OPEN
                "CLOSED" -> CLOSED
                else -> CLOSED
            }
        }
    }
}
