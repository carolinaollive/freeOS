package com.freeos.smstransfer.ui.screens

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
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
class HomeViewModel @Inject constructor(
    private val repository: TransferRepository
) : ViewModel() {
    var transfers by mutableStateOf<List<TransferResponse>>(emptyList())
        private set
    var isLoading by mutableStateOf(true)
        private set

    init {
        loadTransfers()
    }

    fun loadTransfers() {
        viewModelScope.launch {
            isLoading = true
            try {
                transfers = repository.getTransfers()
            } catch (_: Exception) {}
            isLoading = false
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onStartTransfer: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel()
) {
    var hasPermission by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        hasPermission = permissions[Manifest.permission.READ_SMS] == true
        if (hasPermission) onStartTransfer()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("FreeOS Transfer") }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp)
        ) {
            // Main action card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "Transfer Messages",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Read all SMS and MMS from this phone and send them to your iPhone",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(
                        onClick = {
                            permissionLauncher.launch(arrayOf(
                                Manifest.permission.READ_SMS,
                                Manifest.permission.READ_CONTACTS,
                            ))
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp)
                    ) {
                        Text("Start Transfer", fontSize = 16.sp)
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Previous transfers
            Text(
                text = "Previous Transfers",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold
            )

            Spacer(modifier = Modifier.height(8.dp))

            if (viewModel.isLoading) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
            } else if (viewModel.transfers.isEmpty()) {
                Text(
                    text = "No transfers yet",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                LazyColumn {
                    items(viewModel.transfers) { transfer ->
                        TransferCard(transfer)
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
            }
        }
    }
}

@Composable
fun TransferCard(transfer: TransferResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "${transfer.total_messages} messages",
                    fontWeight = FontWeight.SemiBold
                )
                StatusChip(transfer.status)
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "${transfer.sms_count} SMS, ${transfer.mms_count} MMS, ${transfer.rcs_count} RCS",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "${transfer.total_contacts} contacts",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
fun StatusChip(status: String) {
    val (color, label) = when (status) {
        "uploading" -> MaterialTheme.colorScheme.tertiary to "Uploading"
        "ready" -> MaterialTheme.colorScheme.primary to "Ready"
        "downloading" -> MaterialTheme.colorScheme.secondary to "Downloading"
        "completed" -> MaterialTheme.colorScheme.primary to "Done"
        "expired" -> MaterialTheme.colorScheme.error to "Expired"
        else -> MaterialTheme.colorScheme.outline to status
    }
    Surface(
        color = color.copy(alpha = 0.12f),
        shape = MaterialTheme.shapes.small
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            color = color,
            style = MaterialTheme.typography.labelSmall
        )
    }
}
