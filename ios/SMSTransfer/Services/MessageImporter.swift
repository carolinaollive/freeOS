import Foundation

/// Downloads messages from the backend and prepares them for iOS import.
///
/// The iOS app cannot directly write to the Messages database, so this service:
/// 1. Downloads all messages from the transfer
/// 2. Creates a structured export that the companion desktop tool can inject
/// 3. Alternatively, guides the user through a desktop-assisted transfer
@MainActor
class MessageImporter: ObservableObject {
    @Published var phase: ImportPhase = .idle
    @Published var progress: Double = 0
    @Published var detail: String = ""
    @Published var error: String?
    @Published var downloadedMessages: [TransferAPIClient.MessageResponse] = []
    @Published var totalMessages: Int = 0

    enum ImportPhase: Equatable {
        case idle
        case downloading
        case preparing
        case readyForTransfer
        case error
    }

    private let api = TransferAPIClient.shared

    /// Download all messages for a transfer from the backend.
    func downloadMessages(transferId: String) async {
        phase = .downloading
        detail = "Downloading messages..."
        error = nil
        downloadedMessages = []

        do {
            // Get first page to know total
            let firstPage = try await api.getMessages(transferId: transferId, offset: 0, limit: 500)
            totalMessages = firstPage.total
            downloadedMessages.append(contentsOf: firstPage.messages)
            progress = Double(downloadedMessages.count) / Double(totalMessages)

            // Download remaining pages
            while downloadedMessages.count < totalMessages {
                let page = try await api.getMessages(
                    transferId: transferId,
                    offset: downloadedMessages.count,
                    limit: 500
                )
                downloadedMessages.append(contentsOf: page.messages)
                progress = Double(downloadedMessages.count) / Double(totalMessages)
                detail = "Downloaded \(downloadedMessages.count)/\(totalMessages) messages..."
            }

            phase = .preparing
            detail = "Preparing messages for import..."

            // Save messages locally for the desktop companion tool
            try saveMessagesLocally(transferId: transferId)

            phase = .readyForTransfer
            detail = "Messages ready! Connect your iPhone to your computer to complete the transfer."

            // Mark transfer as completed
            _ = try await api.completeTransfer(id: transferId)

        } catch {
            self.error = error.localizedDescription
            phase = .error
        }
    }

    /// Save downloaded messages as NDJSON to the app's documents directory.
    /// The desktop companion tool can read this file to inject into the backup.
    private func saveMessagesLocally(transferId: String) throws {
        let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let exportDir = documentsURL.appendingPathComponent("transfers/\(transferId)")
        try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)

        let messagesURL = exportDir.appendingPathComponent("messages.ndjson")
        var output = ""

        for msg in downloadedMessages {
            var record: [String: Any] = [
                "address": msg.address,
                "date": String(msg.timestampMs),
                "type": msg.isSent ? "2" : "1",
                "body": msg.body,
            ]
            if let subject = msg.subject {
                record["subject"] = subject
            }
            if msg.isGroup {
                record["is_group"] = true
                record["participants"] = msg.participants
            }
            if msg.msgType == "mms" || msg.msgType == "rcs" {
                record["msg_box"] = msg.isSent ? "2" : "1"
                if msg.msgType == "rcs" {
                    record["ct_t"] = "application/vnd.3gpp.sms+rcs"
                }
            }

            if let jsonData = try? JSONSerialization.data(withJSONObject: record),
               let jsonString = String(data: jsonData, encoding: .utf8) {
                output += jsonString + "\n"
            }
        }

        try output.write(to: messagesURL, atomically: true, encoding: .utf8)
    }

    /// Stats for display
    var stats: TransferStats {
        let sms = downloadedMessages.filter { $0.msgType == "sms" }.count
        let mms = downloadedMessages.filter { $0.msgType == "mms" }.count
        let rcs = downloadedMessages.filter { $0.msgType == "rcs" }.count
        let contacts = Set(downloadedMessages.map { $0.address }).count
        let sent = downloadedMessages.filter { $0.isSent }.count
        let received = downloadedMessages.filter { !$0.isSent }.count

        return TransferStats(
            total: downloadedMessages.count,
            sms: sms, mms: mms, rcs: rcs,
            contacts: contacts, sent: sent, received: received
        )
    }

    struct TransferStats {
        let total: Int
        let sms: Int
        let mms: Int
        let rcs: Int
        let contacts: Int
        let sent: Int
        let received: Int
    }
}
