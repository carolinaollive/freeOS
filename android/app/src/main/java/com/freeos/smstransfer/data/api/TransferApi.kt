package com.freeos.smstransfer.data.api

import okhttp3.MultipartBody
import retrofit2.http.*

/**
 * Retrofit interface for the FreeOS Transfer backend API.
 */
interface TransferApi {

    // ── Auth ─────────────────────────────────────────────────────────

    @POST("auth/google")
    suspend fun signInWithGoogle(@Body request: GoogleAuthRequest): AuthResponse

    @GET("auth/me")
    suspend fun getMe(): UserResponse

    // ── Transfers ────────────────────────────────────────────────────

    @POST("transfers")
    suspend fun createTransfer(@Body request: CreateTransferRequest = CreateTransferRequest()): TransferResponse

    @GET("transfers")
    suspend fun listTransfers(): TransferListResponse

    @GET("transfers/{id}")
    suspend fun getTransfer(@Path("id") id: String): TransferResponse

    @POST("transfers/{id}/finalize")
    suspend fun finalizeTransfer(@Path("id") id: String): TransferResponse

    @POST("transfers/{id}/complete")
    suspend fun completeTransfer(@Path("id") id: String): TransferResponse

    // ── Messages ─────────────────────────────────────────────────────

    @POST("transfers/{transferId}/messages")
    suspend fun uploadMessages(
        @Path("transferId") transferId: String,
        @Body batch: MessageBatchUpload
    ): UploadResult

    @Multipart
    @POST("transfers/{transferId}/messages/{messageId}/attachments")
    suspend fun uploadAttachment(
        @Path("transferId") transferId: String,
        @Path("messageId") messageId: String,
        @Part file: MultipartBody.Part
    ): AttachmentUploadResponse
}

// ── Request/Response DTOs ────────────────────────────────────────────

data class GoogleAuthRequest(val id_token: String)

data class AuthResponse(
    val access_token: String,
    val token_type: String,
    val user: UserResponse
)

data class UserResponse(
    val id: String,
    val email: String,
    val name: String,
    val picture_url: String?
)

data class CreateTransferRequest(val placeholder: String = "")

data class TransferResponse(
    val id: String,
    val status: String,
    val created_at: String,
    val expires_at: String,
    val total_messages: Int,
    val sms_count: Int,
    val mms_count: Int,
    val rcs_count: Int,
    val total_contacts: Int,
    val total_attachments: Int,
    val upload_size_bytes: Long
)

data class TransferListResponse(val transfers: List<TransferResponse>)

data class MessageUploadDto(
    val address: String,
    val timestamp_ms: Long,
    val is_sent: Boolean,
    val body: String = "",
    val msg_type: String = "sms",
    val subject: String? = null,
    val is_group: Boolean = false,
    val participants: List<String> = emptyList()
)

data class MessageBatchUpload(val messages: List<MessageUploadDto>)

data class UploadResult(val inserted: Int, val total: Int)

data class AttachmentUploadResponse(val id: String, val upload_url: String)
