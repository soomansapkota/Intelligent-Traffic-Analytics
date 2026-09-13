package com.traffic.analytics.api;

import com.squareup.okhttp3.OkHttpClient;
import com.squareup.okhttp3.logging.HttpLoggingInterceptor;

import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

/**
 * Singleton API client for communicating with Traffic Analytics backend.
 */
public class ApiClient {
    private static TrafficApiService instance = null;
    private static String BASE_URL = "http://0.0.0.0:8000"; // Change to your server IP

    public static TrafficApiService getInstance() {
        if (instance == null) {
            instance = createRetrofit().create(TrafficApiService.class);
        }
        return instance;
    }

    public static void setBaseUrl(String url) {
        BASE_URL = url;
        instance = null; // Reset instance to use new base URL
    }

    private static Retrofit createRetrofit() {
        HttpLoggingInterceptor logging = new HttpLoggingInterceptor();
        logging.setLevel(HttpLoggingInterceptor.Level.BODY);

        OkHttpClient client = new OkHttpClient.Builder()
                .addInterceptor(logging)
                .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .writeTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .build();

        return new Retrofit.Builder()
                .baseUrl(BASE_URL)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build();
    }
}
