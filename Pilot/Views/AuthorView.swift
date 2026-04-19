import SwiftUI

private let SAMPLE_YAML: String = """
name: check-osu-swipes
app: Ohio State
description: Read remaining dining swipes and balance
steps:
  - open_app: Ohio State
  - wait_for: "Welcome back"
  - tap: "Dining"
  - wait_for: "swipes remaining"
  - read:
      field: swipes
      selector: "swipes remaining"
      type: number
  - notify:
      channel: imessage
      body: "{{swipes}} swipes left"
"""

private let EXAMPLE_PROMPTS: [String] = [
    "Check my remaining dining swipes at OSU and text them to me",
    "Every weekday at 7:30am, start my commute playlist on Spotify",
    "Reorder my usual Chipotle bowl from the nearest store via Grubhub",
    "Open Notes and append a blank journal template with today's date",
]

private let APPS: [String] = ["Ohio State", "Grubhub", "Weather", "Spotify", "Notes", "Uber"]

struct AuthorView: View {
    @EnvironmentObject var appState: AppState
    @State private var prompt: String = "Check my remaining dining swipes at OSU and text them to me"
    @State private var yaml: String = SAMPLE_YAML
    @State private var drafting: Bool = false
    @State private var saved: Bool = false
    @State private var saving: Bool = false
    @State private var selectedApp: String = "Ohio State"
    @State private var draftError: String? = nil
    @State private var saveError: String? = nil
    @State private var savedName: String? = nil
    @FocusState private var promptFocused: Bool

    var body: some View {
        // GeometryReader gives us a real 1.0 / 1.2 column ratio — `layoutPriority`
        // doesn't actually allocate fractional widths; it just decides who wins the
        // shrink fight, which crushes the left column when the YAML pane is greedy.
        GeometryReader { geo in
            let gap = PSpace.l
            let leftW = max(360, (geo.size.width - gap) * (1.0 / 2.2))
            let rightW = geo.size.width - gap - leftW
            HStack(alignment: .top, spacing: gap) {
                VStack(spacing: PSpace.l) {
                    describePanel
                    targetAppPanel
                }
                .frame(width: leftW, alignment: .top)

                yamlPanel
                    .frame(width: rightW, alignment: .top)
            }
        }
        .padding(PSpace.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(PColor.bg1)
    }

    private func draft() async {
        guard !prompt.isEmpty, !drafting else { return }
        drafting = true
        defer { drafting = false }
        do {
            let r = try await appState.client.callOnce(method: "workflow.draft",
                                                       params: ["description": prompt])
            if let y = r["yaml"] as? String {
                yaml = y
                draftError = nil
            } else if let e = r["error"] as? String {
                draftError = e
            }
        } catch {
            draftError = "\(error)"
        }
    }

    private func save() async {
        guard !saving else { return }
        saving = true
        defer { saving = false }
        do {
            let r = try await appState.client.callOnce(method: "workflow.save",
                                                       params: ["yaml": yaml])
            if let name = r["name"] as? String {
                savedName = name
                saveError = nil
                saved = true
                appState.workflowsVersion += 1
                await appState.data.refreshWorkflows()
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    saved = false
                }
            } else if let e = r["error"] as? String {
                saveError = e
            }
        } catch {
            saveError = "\(error)"
        }
    }

    private func testRun() async {
        if savedName == nil {
            await save()
        }
        let name = savedName ?? extractedNameFromYAML(yaml)
        let app = extractedAppFromYAML(yaml) ?? selectedApp
        appState.data.startRun(workflowName: name, app: app)
    }

    private func extractedNameFromYAML(_ s: String) -> String {
        for line in s.split(separator: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("name:") {
                return String(trimmed.dropFirst("name:".count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            }
        }
        return "untitled"
    }

    private func extractedAppFromYAML(_ s: String) -> String? {
        for line in s.split(separator: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("app:") {
                let v = String(trimmed.dropFirst("app:".count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                return v.isEmpty ? nil : v
            }
        }
        return nil
    }

    @ViewBuilder
    private var describePanel: some View {
        VStack(alignment: .leading, spacing: PSpace.m) {
            // Title + caption stacked vertically so the title never wraps when the
            // column is narrow. The original HStack layout would split "Describe"
            // across three lines on a 1180px window.
            VStack(alignment: .leading, spacing: 2) {
                Text("Describe the task")
                    .font(PFont.display(14, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                    .lineLimit(1)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Plain English — Claude drafts YAML.")
                    .font(PFont.ui(11.5))
                    .foregroundStyle(PColor.fg2)
                    .lineLimit(1)
            }
            promptEditor
            examplesRow
            HStack(spacing: 8) {
                PButton(drafting ? "Drafting…" : "Draft with Claude",
                        icon: "sparkles",
                        variant: .primary,
                        size: .regular) {
                    Task { await draft() }
                }
                    .opacity(prompt.isEmpty ? 0.5 : 1)
                    .disabled(prompt.isEmpty || drafting)
                PButton("Clear", variant: .ghost, size: .small) { prompt = "" }
                Spacer()
                Text("\(prompt.count)/500")
                    .font(PFont.mono(11))
                    .foregroundStyle(PColor.fg3)
            }
            if let e = draftError {
                Text(e)
                    .font(PFont.ui(11.5))
                    .foregroundStyle(PColor.bad)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(PSpace.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    @ViewBuilder
    private var promptEditor: some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: PRadius.sm + 2)
                .fill(PColor.bg1)
                .overlay(
                    RoundedRectangle(cornerRadius: PRadius.sm + 2)
                        .stroke(promptFocused ? PColor.signal : PColor.line,
                                lineWidth: promptFocused ? 1 : 0.5)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: PRadius.sm + 2)
                        .stroke(PColor.signalDim, lineWidth: promptFocused ? 3 : 0)
                        .blur(radius: promptFocused ? 2 : 0)
                )
            TextEditor(text: $prompt)
                .font(PFont.ui(12.5))
                .foregroundStyle(PColor.fg0)
                .scrollContentBackground(.hidden)
                .padding(8)
                .focused($promptFocused)
            if prompt.isEmpty {
                Text("e.g. Every weekday at 8am, open the Ohio State app and text me my remaining dining swipes.")
                    .font(PFont.ui(12.5))
                    .foregroundStyle(PColor.fg3)
                    .padding(14)
                    .allowsHitTesting(false)
            }
        }
        .frame(minHeight: 96)
    }

    @ViewBuilder
    private var examplesRow: some View {
        // Kicker above chips, not beside, so the flow layout owns full row width.
        VStack(alignment: .leading, spacing: 6) {
            Text("Examples").kicker()
            FlowChips(prompts: EXAMPLE_PROMPTS) { p in
                prompt = p
            }
        }
    }

    @ViewBuilder
    private var targetAppPanel: some View {
        VStack(alignment: .leading, spacing: PSpace.m) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Target app")
                    .font(PFont.display(14, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                    .lineLimit(1)
                Text("Detected from the prompt. Override if needed.")
                    .font(PFont.ui(11.5))
                    .foregroundStyle(PColor.fg2)
                    .lineLimit(1)
            }
            let columns = [GridItem(.flexible(), spacing: 8),
                           GridItem(.flexible(), spacing: 8)]
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(APPS, id: \.self) { a in
                    appPick(a)
                }
            }
        }
        .padding(PSpace.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    @ViewBuilder
    private func appPick(_ a: String) -> some View {
        let active = selectedApp == a
        Button { selectedApp = a } label: {
            HStack(spacing: 8) {
                AppMark(app: a, size: 22)
                Text(a)
                    .font(PFont.ui(12, weight: .medium))
                    .foregroundStyle(active ? PColor.signal : PColor.fg0)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(active ? PColor.signalDim : PColor.bg3)
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.sm)
                    .stroke(active ? PColor.signal.opacity(0.6) : PColor.lineSoft,
                            lineWidth: active ? 1 : 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var yamlPanel: some View {
        VStack(alignment: .leading, spacing: PSpace.m) {
            HStack(alignment: .center, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Workflow YAML")
                        .font(PFont.display(14, weight: .semibold))
                        .foregroundStyle(PColor.fg0)
                        .lineLimit(1)
                    Text("Edit directly if needed.")
                        .font(PFont.ui(11.5))
                        .foregroundStyle(PColor.fg2)
                        .lineLimit(1)
                }
                Spacer()
                if saved, let name = savedName {
                    Chip(text: "Saved as \(name)", tone: .ok, dot: true)
                }
            }
            yamlEditor
            HStack(spacing: 8) {
                PButton(saving ? "Saving…" : "Save to Library",
                        icon: "checkmark", variant: .primary) {
                    Task { await save() }
                }
                .disabled(saving)
                PButton("Test run", icon: "play.fill", variant: .ghost, size: .small) {
                    Task { await testRun() }
                }
                Spacer()
                Text("\(yaml.split(separator: "\n", omittingEmptySubsequences: false).count) lines · valid YAML")
                    .font(PFont.mono(11))
                    .foregroundStyle(PColor.fg3)
            }
            if let e = saveError {
                Text(e)
                    .font(PFont.ui(11.5))
                    .foregroundStyle(PColor.bad)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(PSpace.l)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    @ViewBuilder
    private var yamlEditor: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                let lines = yaml.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
                ForEach(Array(lines.enumerated()), id: \.offset) { i, ln in
                    YamlLineRow(index: i + 1, line: ln)
                }
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(minHeight: 360)
        .background(PColor.bg0)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.md)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }
}

private struct YamlLineRow: View {
    let index: Int
    let line: String

    private static let yamlKeyColor = Color(red: 0.85, green: 0.78, blue: 0.50)
    private static let yamlValColor = Color(red: 0.65, green: 0.78, blue: 0.55)

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(String(format: "%2d", index))
                .font(PFont.mono(11))
                .foregroundStyle(PColor.fg3)
                .frame(width: 20, alignment: .trailing)
            content
                .font(PFont.mono(12))
                .foregroundStyle(PColor.fg1)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 1)
    }

    @ViewBuilder
    private var content: some View {
        if let parts = parse(line) {
            (Text(parts.indent)
                + Text(parts.dash).foregroundColor(PColor.fg3)
                + Text(parts.key).foregroundColor(Self.yamlKeyColor)
                + Text(parts.colon).foregroundColor(PColor.fg2)
                + Text(parts.rest).foregroundColor(Self.yamlValColor))
        } else {
            Text(line)
        }
    }

    private struct Parts {
        let indent: String
        let dash: String
        let key: String
        let colon: String
        let rest: String
    }

    private func parse(_ s: String) -> Parts? {
        // Mirror: ^(\s*)(-?\s*)([\w_-]+)(:)(.*)$
        var i = s.startIndex
        let end = s.endIndex
        var indentEnd = i
        while indentEnd < end, s[indentEnd] == " " || s[indentEnd] == "\t" {
            indentEnd = s.index(after: indentEnd)
        }
        let indent = String(s[i..<indentEnd])
        i = indentEnd
        var dashEnd = i
        if dashEnd < end, s[dashEnd] == "-" {
            dashEnd = s.index(after: dashEnd)
            while dashEnd < end, s[dashEnd] == " " || s[dashEnd] == "\t" {
                dashEnd = s.index(after: dashEnd)
            }
        }
        let dash = String(s[i..<dashEnd])
        i = dashEnd
        var keyEnd = i
        while keyEnd < end {
            let c = s[keyEnd]
            if c.isLetter || c.isNumber || c == "_" || c == "-" {
                keyEnd = s.index(after: keyEnd)
            } else {
                break
            }
        }
        if keyEnd == i { return nil }
        let key = String(s[i..<keyEnd])
        i = keyEnd
        guard i < end, s[i] == ":" else { return nil }
        let colonEnd = s.index(after: i)
        let colon = String(s[i..<colonEnd])
        let rest = String(s[colonEnd..<end])
        return Parts(indent: indent, dash: dash, key: key, colon: colon, rest: rest)
    }
}

