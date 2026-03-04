import SwiftUI

struct ContentView: View {
    @StateObject private var authManager = AuthManager()

    var body: some View {
        Group {
            if authManager.isSignedIn {
                HomeView()
                    .environmentObject(authManager)
            } else {
                SignInView()
                    .environmentObject(authManager)
            }
        }
    }
}
