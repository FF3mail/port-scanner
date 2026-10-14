package com.example.portscanner.util

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.example.portscanner.R
import com.example.portscanner.domain.PortComparison

class NotificationHelper(private val context: Context) {

    fun showScanResults(
        comparisons: List<PortComparison>,
        clientScanError: String?,
    ): Boolean {
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) {
            return false
        }

        createChannelIfNeeded()

        val matches = comparisons.count { it.isMatch }
        val mismatches = comparisons.size - matches

        val bodyLines = comparisons.map { it.formatLine() }.toMutableList()
        if (clientScanError != null) {
            bodyLines.add("")
            bodyLines.add("Ошибка клиентского сканирования: $clientScanError")
        }
        bodyLines.add("")
        bodyLines.add("Совпадений: $matches, Расхождений: $mismatches")

        val bigText = bodyLines.joinToString("\n")

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(TITLE)
            .setContentText(bigText)
            .setStyle(NotificationCompat.BigTextStyle().bigText(bigText))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
        return true
    }

    private fun createChannelIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_ID,
            NotificationManager.IMPORTANCE_HIGH,
        )
        val manager = context.getSystemService(NotificationManager::class.java)
        manager?.createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "port_scanner_channel"
        private const val TITLE = "Результаты сканирования портов"
        private const val NOTIFICATION_ID = 1001
    }
}
