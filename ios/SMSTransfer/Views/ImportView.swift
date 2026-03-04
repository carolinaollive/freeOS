import SwiftUI

/// Shown when the user taps a ready transfer — downloads messages and prepares for import.
struct ImportView: View {
    let transferId: String
    @StateObject private var importer = MessageImporter()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                switch importer.phase {
                case .idle, .downloading:
                    downloadingView

                case .preparing:
                    preparingView

                case .readyForTransfer:
                    readyView

                case .error:
                    errorView
                }
            }
            .padding(32)
            .navigationTitle("Import Messages")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            .task {
                await importer.downloadMessages(transferId: transferId)
            }
        }
    }

    // MARK: - Phase Views

    private var downloadingView: some View {
        VStack(spacing: 16) {
            Spacer()
            ProgressView()
                .scaleEffect(2)
            Text("Downloading Messages")
                .font(.title2)
                .fontWeight(.bold)
                .padding(.top, 16)
            Text(importer.detail)
                .foregroundColor(.secondary)
            if importer.totalMessages > 0 {
                ProgressView(value: importer.progress)
                    .padding(.horizontal)
                Text("\(Int(importer.progress * 100))%")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
    }

    private var preparingView: some View {
        VStack(spacing: 16) {
            Spacer()
            ProgressView()
                .scaleEffect(1.5)
            Text("Preparing...")
                .font(.title3)
                .foregroundColor(.secondary)
            Spacer()
        }
    }

    private var readyView: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 64))
                .foregroundColor(.green)

            Text("Messages Ready!")
                .font(.title)
                .fontWeight(.bold)

            let stats = importer.stats
            VStack(alignment: .leading, spacing: 8) {
                StatRow(label: "Total", value: "\(stats.total)")
                StatRow(label: "SMS", value: "\(stats.sms)")
                StatRow(label: "MMS", value: "\(stats.mms)")
                StatRow(label: "RCS", value: "\(stats.rcs)")
                Divider()
                StatRow(label: "Contacts", value: "\(stats.contacts)")
                StatRow(label: "Sent", value: "\(stats.sent)")
                StatRow(label: "Received", value: "\(stats.received)")
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)

            Text("To finish the transfer:")
                .font(.headline)
                .padding(.top)

            VStack(alignment: .leading, spacing: 12) {
                InstructionRow(number: 1, text: "Connect this iPhone to your Mac or PC via USB")
                InstructionRow(number: 2, text: "On your computer, run:")
                Text("freeos-transfer restore")
                    .font(.system(.body, design: .monospaced))
                    .padding(8)
                    .background(Color(.systemGray5))
                    .cornerRadius(6)
                InstructionRow(number: 3, text: "Your messages will appear in the Messages app")
            }

            Spacer()

            Button("Done") { dismiss() }
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: .infinity)
                .frame(height: 48)
        }
    }

    private var errorView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48))
                .foregroundColor(.red)
            Text("Import Failed")
                .font(.title2)
                .fontWeight(.bold)
            Text(importer.error ?? "Unknown error")
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
            Button("Try Again") {
                Task { await importer.downloadMessages(transferId: transferId) }
            }
            .buttonStyle(.borderedProminent)
        }
    }
}

// MARK: - Helper Views

struct StatRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.semibold)
        }
    }
}

struct InstructionRow: View {
    let number: Int
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(number)")
                .font(.caption)
                .fontWeight(.bold)
                .frame(width: 24, height: 24)
                .background(Color.accentColor.opacity(0.15))
                .foregroundColor(.accentColor)
                .clipShape(Circle())
            Text(text)
                .font(.subheadline)
        }
    }
}
