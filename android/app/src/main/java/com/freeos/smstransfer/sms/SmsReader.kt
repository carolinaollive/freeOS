package com.freeos.smstransfer.sms

import android.content.ContentResolver
import android.database.Cursor
import android.net.Uri
import android.provider.Telephony
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject

/**
 * Reads SMS and MMS messages directly from the Android content provider.
 *
 * No third-party export app needed — we read from the system SMS database
 * using the standard Telephony content URIs.
 */
class SmsReader @Inject constructor(
    private val contentResolver: ContentResolver
) {
    data class SmsMessage(
        val address: String,
        val timestampMs: Long,
        val isSent: Boolean,
        val body: String,
        val msgType: String, // "sms" or "mms"
        val subject: String? = null,
        val isGroup: Boolean = false,
        val participants: List<String> = emptyList(),
        val attachments: List<MmsAttachment> = emptyList()
    )

    data class MmsAttachment(
        val contentType: String,
        val data: ByteArray,
        val filename: String
    )

    data class ReadProgress(
        val phase: String, // "sms" or "mms"
        val current: Int,
        val total: Int
    )

    /**
     * Read all SMS messages from the device.
     *
     * Uses the Telephony.Sms content provider which is available on API 19+.
     * Requires READ_SMS permission.
     */
    suspend fun readAllSms(
        onProgress: (ReadProgress) -> Unit = {}
    ): List<SmsMessage> = withContext(Dispatchers.IO) {
        val messages = mutableListOf<SmsMessage>()

        // Count total for progress
        val total = countMessages(Telephony.Sms.CONTENT_URI)
        var current = 0

        val cursor: Cursor? = contentResolver.query(
            Telephony.Sms.CONTENT_URI,
            arrayOf(
                Telephony.Sms.ADDRESS,
                Telephony.Sms.DATE,
                Telephony.Sms.TYPE,
                Telephony.Sms.BODY,
                Telephony.Sms.SUBJECT,
            ),
            null, null,
            "${Telephony.Sms.DATE} ASC"
        )

        cursor?.use {
            val addressIdx = it.getColumnIndexOrThrow(Telephony.Sms.ADDRESS)
            val dateIdx = it.getColumnIndexOrThrow(Telephony.Sms.DATE)
            val typeIdx = it.getColumnIndexOrThrow(Telephony.Sms.TYPE)
            val bodyIdx = it.getColumnIndexOrThrow(Telephony.Sms.BODY)
            val subjectIdx = it.getColumnIndexOrThrow(Telephony.Sms.SUBJECT)

            while (it.moveToNext()) {
                val address = it.getString(addressIdx) ?: continue
                val date = it.getLong(dateIdx)
                val type = it.getInt(typeIdx)
                val body = it.getString(bodyIdx) ?: ""
                val subject = it.getString(subjectIdx)

                // Type 2 = sent, Type 1 = received (same as Android SMS type constants)
                val isSent = type == Telephony.Sms.MESSAGE_TYPE_SENT

                messages.add(
                    SmsMessage(
                        address = normalizePhone(address),
                        timestampMs = date,
                        isSent = isSent,
                        body = body,
                        msgType = "sms",
                        subject = subject?.takeIf { s -> s.isNotBlank() }
                    )
                )

                current++
                if (current % 100 == 0) {
                    onProgress(ReadProgress("sms", current, total))
                }
            }
        }

        onProgress(ReadProgress("sms", total, total))
        messages
    }

    /**
     * Read all MMS messages from the device.
     *
     * MMS is more complex — we need to read the message metadata, then query
     * the parts table for text and attachments, and the addr table for participants.
     */
    suspend fun readAllMms(
        onProgress: (ReadProgress) -> Unit = {}
    ): List<SmsMessage> = withContext(Dispatchers.IO) {
        val messages = mutableListOf<SmsMessage>()
        val total = countMessages(Telephony.Mms.CONTENT_URI)
        var current = 0

        val cursor = contentResolver.query(
            Telephony.Mms.CONTENT_URI,
            arrayOf(
                Telephony.Mms._ID,
                Telephony.Mms.DATE,
                Telephony.Mms.MESSAGE_BOX,
                Telephony.Mms.SUBJECT,
                Telephony.Mms.CONTENT_TYPE,
            ),
            null, null,
            "${Telephony.Mms.DATE} ASC"
        )

        cursor?.use {
            val idIdx = it.getColumnIndexOrThrow(Telephony.Mms._ID)
            val dateIdx = it.getColumnIndexOrThrow(Telephony.Mms.DATE)
            val boxIdx = it.getColumnIndexOrThrow(Telephony.Mms.MESSAGE_BOX)
            val subjectIdx = it.getColumnIndexOrThrow(Telephony.Mms.SUBJECT)
            val ctIdx = it.getColumnIndex(Telephony.Mms.CONTENT_TYPE)

            while (it.moveToNext()) {
                val mmsId = it.getLong(idIdx)
                val dateSec = it.getLong(dateIdx)
                val msgBox = it.getInt(boxIdx)
                val subject = it.getString(subjectIdx)
                val contentType = if (ctIdx >= 0) it.getString(ctIdx) else null

                // MMS dates are in seconds
                val timestampMs = dateSec * 1000

                val isSent = msgBox == Telephony.Mms.MESSAGE_BOX_SENT
                val isRcs = contentType?.contains("rcs", ignoreCase = true) == true

                // Read participants
                val addresses = readMmsAddresses(mmsId)
                val primaryAddress = if (isSent) {
                    addresses.filter { a -> a.type == MMS_ADDR_TO }.firstOrNull()?.address
                } else {
                    addresses.filter { a -> a.type == MMS_ADDR_FROM }.firstOrNull()?.address
                } ?: addresses.firstOrNull()?.address ?: continue

                val allAddresses = addresses.map { a -> a.address }.distinct()
                val isGroup = allAddresses.size > 2
                val participants = allAddresses.filter { a -> a != primaryAddress }

                // Read parts (text + attachments)
                val parts = readMmsParts(mmsId)
                val bodyParts = parts.filter { p -> p.contentType == "text/plain" }
                val attachments = parts.filter { p ->
                    p.contentType != "text/plain" &&
                    !p.contentType.startsWith("application/smil")
                }

                val body = bodyParts.mapNotNull { p -> p.text }.joinToString("\n")

                messages.add(
                    SmsMessage(
                        address = normalizePhone(primaryAddress),
                        timestampMs = timestampMs,
                        isSent = isSent,
                        body = body,
                        msgType = if (isRcs) "rcs" else "mms",
                        subject = subject?.takeIf { s -> s.isNotBlank() },
                        isGroup = isGroup,
                        participants = participants.map { p -> normalizePhone(p) },
                        attachments = attachments.mapNotNull { p ->
                            p.data?.let { data ->
                                MmsAttachment(
                                    contentType = p.contentType,
                                    data = data,
                                    filename = p.filename ?: "attachment"
                                )
                            }
                        }
                    )
                )

                current++
                if (current % 50 == 0) {
                    onProgress(ReadProgress("mms", current, total))
                }
            }
        }

        onProgress(ReadProgress("mms", total, total))
        messages
    }

    /**
     * Read all messages (SMS + MMS) sorted by timestamp.
     */
    suspend fun readAll(
        onProgress: (ReadProgress) -> Unit = {}
    ): List<SmsMessage> {
        val sms = readAllSms(onProgress)
        val mms = readAllMms(onProgress)
        return (sms + mms).sortedBy { it.timestampMs }
    }

    // ── Internal helpers ────────────────────────────────────────────

    private data class MmsAddress(val address: String, val type: Int)

    private data class MmsPart(
        val contentType: String,
        val text: String?,
        val data: ByteArray?,
        val filename: String?
    )

    private fun readMmsAddresses(mmsId: Long): List<MmsAddress> {
        val addresses = mutableListOf<MmsAddress>()
        val uri = Uri.parse("content://mms/$mmsId/addr")

        contentResolver.query(
            uri,
            arrayOf("address", "type"),
            null, null, null
        )?.use { cursor ->
            val addrIdx = cursor.getColumnIndexOrThrow("address")
            val typeIdx = cursor.getColumnIndexOrThrow("type")

            while (cursor.moveToNext()) {
                val addr = cursor.getString(addrIdx) ?: continue
                if (addr == "insert-address-token") continue
                addresses.add(MmsAddress(addr, cursor.getInt(typeIdx)))
            }
        }

        return addresses
    }

    private fun readMmsParts(mmsId: Long): List<MmsPart> {
        val parts = mutableListOf<MmsPart>()
        val uri = Uri.parse("content://mms/part")

        contentResolver.query(
            uri,
            arrayOf("_id", "ct", "text", "cl", "name", "_data"),
            "mid=$mmsId",
            null, null
        )?.use { cursor ->
            val idIdx = cursor.getColumnIndexOrThrow("_id")
            val ctIdx = cursor.getColumnIndexOrThrow("ct")
            val textIdx = cursor.getColumnIndexOrThrow("text")
            val clIdx = cursor.getColumnIndex("cl")
            val nameIdx = cursor.getColumnIndex("name")

            while (cursor.moveToNext()) {
                val partId = cursor.getLong(idIdx)
                val ct = cursor.getString(ctIdx) ?: continue
                val text = cursor.getString(textIdx)
                val cl = if (clIdx >= 0) cursor.getString(clIdx) else null
                val name = if (nameIdx >= 0) cursor.getString(nameIdx) else null

                var data: ByteArray? = null
                if (ct != "text/plain" && !ct.startsWith("application/smil")) {
                    data = readPartData(partId)
                }

                parts.add(MmsPart(ct, text, data, name ?: cl))
            }
        }

        return parts
    }

    private fun readPartData(partId: Long): ByteArray? {
        return try {
            val uri = Uri.parse("content://mms/part/$partId")
            contentResolver.openInputStream(uri)?.use { it.readBytes() }
        } catch (e: Exception) {
            null
        }
    }

    private fun countMessages(uri: Uri): Int {
        return contentResolver.query(uri, arrayOf("_id"), null, null, null)?.use {
            it.count
        } ?: 0
    }

    companion object {
        const val MMS_ADDR_FROM = 137
        const val MMS_ADDR_TO = 151

        fun normalizePhone(number: String): String {
            val trimmed = number.trim()
            return if (trimmed.startsWith("+")) {
                "+" + trimmed.substring(1).replace(Regex("[^\\d]"), "")
            } else {
                trimmed.replace(Regex("[^\\d]"), "")
            }
        }
    }
}
