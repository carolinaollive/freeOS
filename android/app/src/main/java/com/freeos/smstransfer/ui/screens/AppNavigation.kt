package com.freeos.smstransfer.ui.screens

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

@Composable
fun AppNavigation() {
    val navController = rememberNavController()

    NavHost(navController = navController, startDestination = "sign_in") {
        composable("sign_in") {
            SignInScreen(
                onSignedIn = { navController.navigate("home") { popUpTo("sign_in") { inclusive = true } } }
            )
        }
        composable("home") {
            HomeScreen(
                onStartTransfer = { navController.navigate("transfer") }
            )
        }
        composable("transfer") {
            TransferScreen(
                onComplete = { navController.navigate("home") { popUpTo("home") { inclusive = true } } }
            )
        }
    }
}
