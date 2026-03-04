import SwiftUI

struct SignInView: View {
    @EnvironmentObject var authManager: AuthManager

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            Text("FreeOS")
                .font(.system(size: 48, weight: .bold))
                .foregroundColor(.accentColor)

            Text("Transfer your messages\nfrom Android to iPhone")
                .multilineTextAlignment(.center)
                .font(.title3)
                .foregroundColor(.secondary)
                .padding(.top, 8)

            Spacer()

            if authManager.isLoading {
                ProgressView()
                    .scaleEffect(1.5)
            } else {
                Button(action: {
                    // Get the root view controller for Google Sign-In presentation
                    if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                       let viewController = windowScene.windows.first?.rootViewController {
                        authManager.signInWithGoogle(presenting: viewController)
                    }
                }) {
                    HStack {
                        Image(systemName: "person.circle.fill")
                        Text("Sign in with Google")
                    }
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                }
                .buttonStyle(.borderedProminent)
                .padding(.horizontal, 32)
            }

            if let error = authManager.error {
                Text(error)
                    .foregroundColor(.red)
                    .font(.caption)
                    .padding(.top, 12)
            }

            Spacer()

            Text("Free and open source. Your messages are encrypted\nin transit and auto-deleted after 72 hours.")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.bottom, 32)
        }
        .padding()
    }
}
