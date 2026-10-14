package com.example.portscanner.domain

/**
 * Ответ сервера POST /scan.
 */
data class ScanResult(
    val results: Map<Int, String>,
)
