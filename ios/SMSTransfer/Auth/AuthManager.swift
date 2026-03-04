import Foundation
import GoogleSignIn
import Combine

/// Manages Google Sign-In and JWT token lifecycle.
@MainActor
class AuthManager: ObservableObject {
    @Published var isSignedIn = false
    @Published var currentUser: UserInfo?
    @Published var isLoading = false
    @Published var error: String?

    private let api = TransferAPIClient.shared

    struct UserInfo {
        let id: String
        let email: String
        let name: String
        let pictureURL: String?
    }

    func signInWithGoogle(presenting viewController: UIViewController) {
        isLoading = true
        error = nil

        let config = GIDConfiguration(clientID: AppConfig.googleClientID)
        GIDSignIn.sharedInstance.configuration = config

        GIDSignIn.sharedInstance.signIn(withPresenting: viewController) { [weak self] result, signInError in
            guard let self = self else { return }

            if let signInError = signInError {
                self.error = signInError.localizedDescription
                self.isLoading = false
                return
            }

            guard let idToken = result?.user.idToken?.tokenString else {
                self.error = "Failed to get Google ID token"
                self.isLoading = false
                return
            }

            Task {
                await self.authenticateWithBackend(idToken: idToken)
            }
        }
    }

    private func authenticateWithBackend(idToken: String) async {
        do {
            let response = try await api.signIn(googleIdToken: idToken)
            api.setAccessToken(response.accessToken)
            currentUser = UserInfo(
                id: response.user.id,
                email: response.user.email,
                name: response.user.name,
                pictureURL: response.user.pictureURL
            )
            isSignedIn = true
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func signOut() {
        GIDSignIn.sharedInstance.signOut()
        api.setAccessToken(nil)
        isSignedIn = false
        currentUser = nil
    }
}
