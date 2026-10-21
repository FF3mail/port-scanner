package com.example.portscanner.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NetworkClientHttpTimeoutTest {

    @Test
    fun httpReadTimeoutCoversDocumentedWorstCaseServerScan() {
        val worstCaseScanMs = NetworkClient.MAX_PORTS * NetworkClient.SERVER_SCAN_TIMEOUT_PER_PORT_MS
        assertEquals(
            worstCaseScanMs + NetworkClient.HTTP_READ_SAFETY_MARGIN_MS,
            NetworkClient.HTTP_READ_TIMEOUT_MS,
        )
        assertTrue(NetworkClient.HTTP_READ_TIMEOUT_MS > NetworkClient.CONNECT_TIMEOUT_MS)
        assertTrue(NetworkClient.HTTP_READ_TIMEOUT_MS >= 30_000L)
    }

    @Test
    fun connectAndReadTimeoutsAreConfiguredIndependently() {
        assertEquals(3000L, NetworkClient.CONNECT_TIMEOUT_MS)
        assertTrue(NetworkClient.HTTP_READ_TIMEOUT_MS > NetworkClient.CONNECT_TIMEOUT_MS)
    }
}
