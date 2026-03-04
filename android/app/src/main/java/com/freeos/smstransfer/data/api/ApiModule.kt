package com.freeos.smstransfer.data.api

import android.content.ContentResolver
import android.content.Context
import com.freeos.smstransfer.BuildConfig
import com.freeos.smstransfer.sms.SmsReader
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object ApiModule {

    @Provides
    @Singleton
    fun provideTokenHolder(): TokenHolder = TokenHolder()

    @Provides
    @Singleton
    fun provideOkHttpClient(tokenHolder: TokenHolder): OkHttpClient {
        val authInterceptor = Interceptor { chain ->
            val request = tokenHolder.token?.let { token ->
                chain.request().newBuilder()
                    .addHeader("Authorization", "Bearer $token")
                    .build()
            } ?: chain.request()
            chain.proceed(request)
        }

        return OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .addInterceptor(HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
                else HttpLoggingInterceptor.Level.NONE
            })
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit {
        return Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL + "/")
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    @Provides
    @Singleton
    fun provideTransferApi(retrofit: Retrofit): TransferApi {
        return retrofit.create(TransferApi::class.java)
    }

    @Provides
    @Singleton
    fun provideContentResolver(@ApplicationContext context: Context): ContentResolver {
        return context.contentResolver
    }

    @Provides
    @Singleton
    fun provideSmsReader(contentResolver: ContentResolver): SmsReader {
        return SmsReader(contentResolver)
    }
}

/**
 * Simple mutable holder for the JWT access token.
 * Set after Google Sign-In succeeds.
 */
class TokenHolder {
    var token: String? = null
}
