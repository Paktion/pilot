import SwiftUI

struct AuthoringView: View {
    @EnvironmentObject var appState: AppState
    @State private var prompt: String = ""
    @State private var yaml: String = ""
    @State private var isDrafting: Bool = false
    @State private var saveError: String?
    @State private var savedName: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Author").font(.title2).bold()

            VStack(alignment: .leading) {
                Text("Describe the task").font(.headline)
                TextEditor(text: $prompt)
                    .font(.body.monospaced())
                    .frame(minHeight: 80)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.separator))
            }

            HStack {
                Button {
                    Task { await draft() }
                } label: {
                    if isDrafting { ProgressView() } else { Text("Draft workflow") }
                }
                .disabled(isDrafting || prompt.isEmpty)

                Button("Save") { Task { await save() } }
                    .disabled(yaml.isEmpty)
            }

            if let saveError {
                Text(saveError).foregroundStyle(.red).font(.caption)
            }
            if let savedName {
                Text("Saved as: \(savedName)").foregroundStyle(.green).font(.caption)
            }

            VStack(alignment: .leading) {
                Text("YAML draft (editable)").font(.headline)
                TextEditor(text: $yaml)
                    .font(.body.monospaced())
                    .frame(minHeight: 220)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.separator))
            }
            Spacer()
        }
        .padding()
    }

    private func draft() async {
        saveError = nil
        savedName = nil
        isDrafting = true
        defer { isDrafting = false }
        if !appState.client.isConnected {
            await appState.client.connect()
        }
        do {
            let result = try await appState.client.callOnce(
                method: "workflow.draft",
                params: ["description": prompt]
            )
            if let draftedYaml = result["yaml"] as? String {
                self.yaml = draftedYaml
            } else if let err = result["error"] as? String {
                self.saveError = err
            }
        } catch {
            self.saveError = "\(error)"
        }
    }

    private func save() async {
        saveError = nil
        savedName = nil
        do {
            let result = try await appState.client.callOnce(
                method: "workflow.save",
                params: ["yaml": yaml]
            )
            if let name = result["name"] as? String {
                self.savedName = name
            } else if let err = result["error"] as? String {
                self.saveError = err
            }
        } catch {
            self.saveError = "\(error)"
        }
    }
}
