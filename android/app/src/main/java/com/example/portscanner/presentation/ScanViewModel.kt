package com.example.portscanner.presentation

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.portscanner.data.NetworkClient
import com.example.portscanner.data.ScanEndpointParser
import com.example.portscanner.data.ServerHttpException
import com.example.portscanner.data.ServerUnreachableException
import com.example.portscanner.data.UnauthorizedException
import com.example.portscanner.domain.PortComparison
import com.example.portscanner.domain.PortStatus
import kotlinx.coroutines.async
import kotlinx.coroutines.launch

sealed class ScanUiEvent {
    data class ToastMessage(val text: String) : ScanUiEvent()

    data class ShowNotification(
        val comparisons: List<PortComparison>,
        val clientScanError: String?,
    ) : ScanUiEvent()
}

class ScanViewModel(
    private val networkClient: NetworkClient = NetworkClient(),
) : ViewModel() {

    private val _isLoading = MutableLiveData(false)
    val isLoading: LiveData<Boolean> = _isLoading

    private val _uiEvent = MutableLiveData<ScanUiEvent?>()
    val uiEvent: LiveData<ScanUiEvent?> = _uiEvent

    fun consumeUiEvent() {
        _uiEvent.value = null
    }

    fun startScan(
        serverHost: String,
        serverHttpsPort: String,
        token: String,
        portsInput: String,
    ) {
        if (_isLoading.value == true) {
            return
        }

        val endpoint = when (val endpointResult = ScanEndpointParser.parse(serverHost, serverHttpsPort)) {
            is ScanEndpointParser.Result.Error -> {
                emitToast(endpointResult.message)
                return
            }
            is ScanEndpointParser.Result.Ok -> endpointResult.endpoint
        }

        if (token.isBlank()) {
            emitToast("Введите токен авторизации")
            return
        }

        if (portsInput.isBlank()) {
            emitToast("Введите список портов")
            return
        }

        val ports = parsePorts(portsInput)
        if (ports == null) {
            return
        }

        viewModelScope.launch {
            _isLoading.value = true
            try {
                val serverDeferred = async { networkClient.postScan(endpoint, token.trim(), ports) }
                val clientDeferred = async {
                    runCatching { networkClient.scanPorts(endpoint, ports) }
                }

                val serverResult = try {
                    serverDeferred.await()
                } catch (_: ServerUnreachableException) {
                    emitToast("Сервер недоступен")
                    return@launch
                } catch (_: UnauthorizedException) {
                    emitToast("Неверный токен")
                    return@launch
                } catch (e: ServerHttpException) {
                    emitToast(e.message ?: "Ошибка сервера")
                    return@launch
                } catch (e: Exception) {
                    emitToast(e.message ?: "Ошибка сервера")
                    return@launch
                }

                val clientScan = clientDeferred.await()
                val clientResults = clientScan.getOrElse { emptyMap() }
                val clientScanError = clientScan.exceptionOrNull()?.message

                val comparisons = ports.map { port ->
                    val serverStatus = PortStatus.fromRaw(serverResult.results[port])
                    val clientStatus = PortStatus.fromRaw(clientResults[port])
                    PortComparison(port, serverStatus, clientStatus)
                }

                _uiEvent.value = ScanUiEvent.ShowNotification(comparisons, clientScanError)
            } finally {
                _isLoading.value = false
            }
        }
    }

    private fun parsePorts(input: String): List<Int>? {
        val tokens = input.split(',')
            .map { it.trim() }
            .filter { it.isNotEmpty() }

        if (tokens.isEmpty()) {
            emitToast("Список портов пуст")
            return null
        }

        if (tokens.size > NetworkClient.MAX_PORTS) {
            emitToast("Не больше ${NetworkClient.MAX_PORTS} портов")
            return null
        }

        val ports = mutableListOf<Int>()
        for (token in tokens) {
            val port = token.toIntOrNull()
            if (port == null || port !in 1..65535) {
                emitToast("Некорректный порт: $token")
                return null
            }
            ports.add(port)
        }
        return ports
    }

    private fun emitToast(message: String) {
        _uiEvent.value = ScanUiEvent.ToastMessage(message)
    }
}
