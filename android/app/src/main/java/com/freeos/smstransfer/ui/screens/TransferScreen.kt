package com.freeos.smstransfer.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.freeos.smstransfer.data.api.TransferResponse
import com.freeos.smstransfer.data.repository.TransferRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class TransferViewModel @Inject constructor(
    private val repository: TransferRepository
) : ViewModel() {
    var phase by mutableStateOf("starting")
        private set
    var progress by mutableStateOf(0f)
        private set
    var detail by mutableStateOf("Preparing...")
        private set
    var error by mutableStateOf<String?>(null)
        private set
    var result by mutableStateOf<TransferResponse?>(null)
        private set

    init {
        startTransfer()
    }

    private fun startTransfer() {
        viewModelScope.launch {
            try {
                val response = repository.transferAll { p ->
                    phase = p.phase
                    detail = p.detail
                    progress = if (p.total > 0) p.current.toFloat() / p.total else 0f
                }
                result = response
                phase = "done"
                detail = "Transfer complete!"
            } catch (e: Exception) {
                error = e.message ?: "Transfer failed"
                phase = "error"
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransferScreen(
    onComplete: () -> Unit,
    viewModel: TransferViewModel = hiltViewModel()
) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Transferring...") })
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            when (viewModel.phase) {
                "done" -> {
                    val result = viewModel.result
                    Text(
                        text = "Transfer Ready!",
                        fontSize = 28.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    if (result != null) {
                        Text(
                            text = "${result.total_messages} messages uploaded",
                            style = MaterialTheme.typography.titleMedium
                        )
                        Text(
                            text = "${result.sms_count} SMS, ${result.mms_count} MMS, ${result.rcs_count} RCS",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${result.total_contacts} contacts",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Spacer(modifier = Modifier.height(24.dp))
                    Text(
                        text = "Now open the FreeOS app on your iPhone\nand sign in with the same Google account\nto complete the transfer.",
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodyLarge
                    )
                    Spacer(modifier = Modifier.height(32.dp))
                    Button(
                        onClick = onComplete,
                        modifier = Modifier.fillMaxWidth().height(48.dp)
                    ) {
                        Text("Done")
                    }
                }

                "error" -> {
                    Text(
                        text = "Transfer Failed",
                        fontSize = 28.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = viewModel.error ?: "Unknown error",
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.error
                    )
                    Spacer(modifier = Modifier.height(32.dp))
                    OutlinedButton(
                        onClick = onComplete,
                        modifier = Modifier.fillMaxWidth().height(48.dp)
                    ) {
                        Text("Go Back")
                    }
                }

                else -> {
                    // In progress
                    CircularProgressIndicator(
                        modifier = Modifier.size(80.dp),
                        strokeWidth = 6.dp
                    )
                    Spacer(modifier = Modifier.height(32.dp))

                    Text(
                        text = phaseLabel(viewModel.phase),
                        fontSize = 20.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = viewModel.detail,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(16.dp))

                    if (viewModel.progress > 0f) {
                        LinearProgressIndicator(
                            progress = { viewModel.progress },
                            modifier = Modifier.fillMaxWidth().height(8.dp),
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "${(viewModel.progress * 100).toInt()}%",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }
}

private fun phaseLabel(phase: String): String = when (phase) {
    "starting" -> "Preparing..."
    "reading_sms" -> "Reading SMS"
    "reading_mms" -> "Reading MMS"
    "uploading" -> "Uploading"
    "finalizing" -> "Finalizing"
    else -> "Working..."
}
