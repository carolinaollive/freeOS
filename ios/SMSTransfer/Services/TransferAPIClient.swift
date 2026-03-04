import Foundation

/// HTTP client for the FreeOS Transfer backend API.
actor TransferAPIClient {
    static let shared = TransferAPIClient()

    private let baseURL: URL
    private var accessToken: String?
    private let session: URLSession

    private init() {
        self.baseURL = URL(string: AppConfig.apiBaseURL)!
        self.session = URLSession(configuration: .default)
    }

    func setAccessToken(_ token: String?) {
        self.accessToken = token
    }

    // MARK: - Auth

    struct AuthResponse: Decodable {
        let accessToken: String
        let tokenType: String
        let user: UserResponse

        enum CodingKeys: String, CodingKey {
            case accessToken = "access_token"
            case tokenType = "token_type"
            case user
        }
    }

    struct UserResponse: Decodable {
        let id: String
        let email: String
        let name: String
        let pictureURL: String?

        enum CodingKeys: String, CodingKey {
            case id, email, name
            case pictureURL = "picture_url"
        }
    }

    func signIn(googleIdToken: String) async throws -> AuthResponse {
        let body = ["id_token": googleIdToken]
        return try await post("/auth/google", body: body)
    }

    // MARK: - Transfers

    struct TransferResponse: Decodable, Identifiable {
        let id: String
        let status: String
        let createdAt: String
        let expiresAt: String
        let totalMessages: Int
        let smsCount: Int
        let mmsCount: Int
        let rcsCount: Int
        let totalContacts: Int
        let totalAttachments: Int
        let uploadSizeBytes: Int64

        enum CodingKeys: String, CodingKey {
            case id, status
            case createdAt = "created_at"
            case expiresAt = "expires_at"
            case totalMessages = "total_messages"
            case smsCount = "sms_count"
            case mmsCount = "mms_count"
            case rcsCount = "rcs_count"
            case totalContacts = "total_contacts"
            case totalAttachments = "total_attachments"
            case uploadSizeBytes = "upload_size_bytes"
        }
    }

    struct TransferListResponse: Decodable {
        let transfers: [TransferResponse]
    }

    func listTransfers() async throws -> [TransferResponse] {
        let response: TransferListResponse = try await get("/transfers")
        return response.transfers
    }

    func getTransfer(id: String) async throws -> TransferResponse {
        return try await get("/transfers/\(id)")
    }

    func completeTransfer(id: String) async throws -> TransferResponse {
        return try await post("/transfers/\(id)/complete", body: Optional<[String: String]>.none)
    }

    // MARK: - Messages

    struct MessageResponse: Decodable, Identifiable {
        let id: String
        let address: String
        let timestampMs: Int64
        let isSent: Bool
        let body: String
        let msgType: String
        let subject: String?
        let isGroup: Bool
        let participants: [String]
        let attachments: [AttachmentResponse]

        enum CodingKeys: String, CodingKey {
            case id, address, body, subject, participants, attachments
            case timestampMs = "timestamp_ms"
            case isSent = "is_sent"
            case msgType = "msg_type"
            case isGroup = "is_group"
        }
    }

    struct AttachmentResponse: Decodable, Identifiable {
        let id: String
        let contentType: String
        let filename: String
        let sizeBytes: Int64
        let downloadURL: String?

        enum CodingKeys: String, CodingKey {
            case id, filename
            case contentType = "content_type"
            case sizeBytes = "size_bytes"
            case downloadURL = "download_url"
        }
    }

    struct MessageBatchResponse: Decodable {
        let messages: [MessageResponse]
        let total: Int
        let offset: Int
        let limit: Int
    }

    func getMessages(transferId: String, offset: Int = 0, limit: Int = 500) async throws -> MessageBatchResponse {
        return try await get("/transfers/\(transferId)/messages?offset=\(offset)&limit=\(limit)")
    }

    func getAttachmentDownloadURL(transferId: String, messageId: String, attachmentId: String) async throws -> String {
        struct Response: Decodable { let download_url: String }
        let resp: Response = try await get(
            "/transfers/\(transferId)/messages/\(messageId)/attachments/\(attachmentId)/download"
        )
        return resp.download_url
    }

    // MARK: - HTTP helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "GET"
        addAuth(&request)
        let (data, _) = try await session.data(for: request)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B?) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }
        let (data, _) = try await session.data(for: request)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func addAuth(_ request: inout URLRequest) {
        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
    }
}
