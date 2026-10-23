package com.example.portscanner.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ScanEndpointParserTest {

    @Test
    fun buildScanUrl_defaultPort443() {
        val url = ScanEndpointParser.buildHttpsScanUrl("scanner.example.com", 443)
        assertEquals("https://scanner.example.com:443/scan", url)
    }

    @Test
    fun parse_emptyHttpsPort_usesDefault443() {
        val result = ScanEndpointParser.parse("scanner.example.com", "")
        assertTrue(result is ScanEndpointParser.Result.Ok)
        val endpoint = (result as ScanEndpointParser.Result.Ok).endpoint
        assertEquals(443, endpoint.httpsPort)
        assertEquals("https://scanner.example.com:443/scan", endpoint.scanUrlString())
    }

    @Test
    fun buildScanUrl_customPort() {
        val result = ScanEndpointParser.parse("scanner.example.com", "8443")
        assertTrue(result is ScanEndpointParser.Result.Ok)
        val endpoint = (result as ScanEndpointParser.Result.Ok).endpoint
        assertEquals(8443, endpoint.httpsPort)
        assertEquals("https://scanner.example.com:8443/scan", endpoint.scanUrlString())
    }

    @Test
    fun parse_ipv4Literal() {
        val result = ScanEndpointParser.parse("192.168.1.10", "443")
        assertTrue(result is ScanEndpointParser.Result.Ok)
        assertEquals(
            "https://192.168.1.10:443/scan",
            (result as ScanEndpointParser.Result.Ok).endpoint.scanUrlString(),
        )
    }

    @Test
    fun parse_bracketedIpv6() {
        val result = ScanEndpointParser.parse("[::1]", "")
        assertTrue(result is ScanEndpointParser.Result.Ok)
        val endpoint = (result as ScanEndpointParser.Result.Ok).endpoint
        assertEquals("https://[::1]:443/scan", endpoint.scanUrlString())
        assertEquals("::1", endpoint.socketHost())
    }

    @Test
    fun parse_unbracketedIpv6Loopback() {
        val result = ScanEndpointParser.parse("::1", "443")
        assertTrue(result is ScanEndpointParser.Result.Ok)
        assertEquals(
            "https://[::1]:443/scan",
            (result as ScanEndpointParser.Result.Ok).endpoint.scanUrlString(),
        )
    }

    @Test
    fun parse_rejectsHttpSchemeInHost() {
        val result = ScanEndpointParser.parse("https://evil.example.com", "443")
        assertTrue(result is ScanEndpointParser.Result.Error)
    }

    @Test
    fun parse_rejectsUserInfoAndPathInjection() {
        assertTrue(ScanEndpointParser.parse("host@evil", "443") is ScanEndpointParser.Result.Error)
        assertTrue(ScanEndpointParser.parse("host/evil", "443") is ScanEndpointParser.Result.Error)
        assertTrue(ScanEndpointParser.parse("host?x=1", "443") is ScanEndpointParser.Result.Error)
    }

    @Test
    fun parse_rejectsInvalidPort() {
        assertTrue(ScanEndpointParser.parse("scanner.example.com", "0") is ScanEndpointParser.Result.Error)
        assertTrue(ScanEndpointParser.parse("scanner.example.com", "70000") is ScanEndpointParser.Result.Error)
        assertTrue(ScanEndpointParser.parse("scanner.example.com", "abc") is ScanEndpointParser.Result.Error)
    }

    @Test
    fun parse_rejectsEmptyHost() {
        assertTrue(ScanEndpointParser.parse("  ", "443") is ScanEndpointParser.Result.Error)
    }
}
