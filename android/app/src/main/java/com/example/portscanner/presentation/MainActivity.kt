package com.example.portscanner.presentation

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.example.portscanner.R
import com.example.portscanner.util.NotificationHelper

class MainActivity : AppCompatActivity() {

    private val viewModel: ScanViewModel by viewModels()

    private lateinit var editServerIp: EditText
    private lateinit var editToken: EditText
    private lateinit var editPorts: EditText
    private lateinit var buttonStartScan: Button
    private lateinit var progressBar: ProgressBar

    private val notificationHelper by lazy { NotificationHelper(this) }

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, "Разрешение на уведомления не выдано", Toast.LENGTH_SHORT).show()
        }
        pendingNotification?.let { payload ->
            if (granted) {
                showNotificationIfAllowed(payload)
            }
            pendingNotification = null
        }
    }

    private var pendingNotification: ScanUiEvent.ShowNotification? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        editServerIp = findViewById(R.id.editServerIp)
        editToken = findViewById(R.id.editToken)
        editPorts = findViewById(R.id.editPorts)
        buttonStartScan = findViewById(R.id.buttonStartScan)
        progressBar = findViewById(R.id.progressBar)

        buttonStartScan.setOnClickListener {
            viewModel.startScan(
                editServerIp.text.toString(),
                editToken.text.toString(),
                editPorts.text.toString(),
            )
        }

        viewModel.isLoading.observe(this) { loading ->
            val isLoading = loading == true
            progressBar.visibility = if (isLoading) View.VISIBLE else View.GONE
            buttonStartScan.isEnabled = !isLoading
        }

        viewModel.uiEvent.observe(this) { event ->
            if (event == null) {
                return@observe
            }
            when (event) {
                is ScanUiEvent.ToastMessage -> {
                    Toast.makeText(this, event.text, Toast.LENGTH_SHORT).show()
                }
                is ScanUiEvent.ShowNotification -> {
                    requestNotificationAndShow(event)
                }
            }
            viewModel.consumeUiEvent()
        }
    }

    private fun requestNotificationAndShow(event: ScanUiEvent.ShowNotification) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            if (!showNotificationIfAllowed(event)) {
                Toast.makeText(this, "Уведомления отключены", Toast.LENGTH_SHORT).show()
            }
            return
        }

        when {
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.POST_NOTIFICATIONS,
            ) == PackageManager.PERMISSION_GRANTED -> {
                if (!showNotificationIfAllowed(event)) {
                    Toast.makeText(this, "Уведомления отключены", Toast.LENGTH_SHORT).show()
                }
            }
            else -> {
                pendingNotification = event
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun showNotificationIfAllowed(event: ScanUiEvent.ShowNotification): Boolean {
        return notificationHelper.showScanResults(
            comparisons = event.comparisons,
            clientScanError = event.clientScanError,
        )
    }
}
