import SwiftUI

struct HomeView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var transfers: [TransferAPIClient.TransferResponse] = []
    @State private var isLoading = true
    @State private var selectedTransfer: TransferAPIClient.TransferResponse?
    @State private var showingImport = false

    var body: some View {
        NavigationStack {
            List {
                // Pending transfers ready for download
                let readyTransfers = transfers.filter { $0.status == "ready" || $0.status == "downloading" }
                if !readyTransfers.isEmpty {
                    Section("Ready to Import") {
                        ForEach(readyTransfers) { transfer in
                            TransferRow(transfer: transfer)
                                .onTapGesture {
                                    selectedTransfer = transfer
                                    showingImport = true
                                }
                        }
                    }
                }

                // Completed transfers
                let completedTransfers = transfers.filter { $0.status == "completed" }
                if !completedTransfers.isEmpty {
                    Section("Completed") {
                        ForEach(completedTransfers) { transfer in
                            TransferRow(transfer: transfer)
                        }
                    }
                }

                if transfers.isEmpty && !isLoading {
                    Section {
                        VStack(spacing: 12) {
                            Image(systemName: "message.fill")
                                .font(.system(size: 48))
                                .foregroundColor(.secondary)
                            Text("No transfers yet")
                                .font(.headline)
                            Text("Open the FreeOS app on your Android phone to start a transfer, then come back here.")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    }
                }
            }
            .navigationTitle("FreeOS Transfer")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Sign Out") {
                        authManager.signOut()
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: loadTransfers) {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .refreshable {
                await loadTransfersAsync()
            }
            .sheet(isPresented: $showingImport) {
                if let transfer = selectedTransfer {
                    ImportView(transferId: transfer.id)
                }
            }
            .task {
                await loadTransfersAsync()
            }
        }
    }

    private func loadTransfers() {
        Task { await loadTransfersAsync() }
    }

    private func loadTransfersAsync() async {
        isLoading = true
        do {
            transfers = try await TransferAPIClient.shared.listTransfers()
        } catch {}
        isLoading = false
    }
}

struct TransferRow: View {
    let transfer: TransferAPIClient.TransferResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(transfer.totalMessages) messages")
                    .font(.headline)
                Spacer()
                StatusBadge(status: transfer.status)
            }
            Text("\(transfer.smsCount) SMS, \(transfer.mmsCount) MMS, \(transfer.rcsCount) RCS")
                .font(.caption)
                .foregroundColor(.secondary)
            Text("\(transfer.totalContacts) contacts")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 4)
    }
}

struct StatusBadge: View {
    let status: String

    var body: some View {
        Text(label)
            .font(.caption2)
            .fontWeight(.semibold)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundColor(color)
            .clipShape(Capsule())
    }

    private var label: String {
        switch status {
        case "ready": return "Ready"
        case "downloading": return "Downloading"
        case "completed": return "Done"
        case "expired": return "Expired"
        default: return status.capitalized
        }
    }

    private var color: Color {
        switch status {
        case "ready": return .blue
        case "downloading": return .orange
        case "completed": return .green
        case "expired": return .red
        default: return .gray
        }
    }
}
