package com.example.portscanner.data

import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

class NetworkClientPostScanTransportFailureTest {

    @Test
    fun unknownHostException_mapsToServerUnreachable() {
        val mapped = mapPostScanTransportFailure(UnknownHostException("no-such-host.example"))
        assertTrue(mapped is ServerUnreachableException)
    }

    @Test
    fun connectException_mapsToServerUnreachable() {
        val mapped = mapPostScanTransportFailure(ConnectException("refused"))
        assertTrue(mapped is ServerUnreachableException)
    }

    @Test
    fun socketTimeoutException_mapsToServerUnreachable() {
        val mapped = mapPostScanTransportFailure(SocketTimeoutException("timed out"))
        assertTrue(mapped is ServerUnreachableException)
    }

    @Test
    fun otherIOException_passesThroughUnchanged() {
        val original = IOException("unexpected")
        assertSame(original, mapPostScanTransportFailure(original))
    }
}
