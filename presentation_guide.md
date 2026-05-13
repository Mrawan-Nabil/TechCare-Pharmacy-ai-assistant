# 🏥 TechCare Admin Dashboard — Presentation Guide
### *A Simple Guide for Presenting to Judges*

---

## 1. The Big Picture — The Analogy

> **Start your presentation with this — it sets the scene for everything else.**

Imagine a busy hospital pharmacy. At the front counter, there's a **Cashier** — they check every prescription that comes in, make sure the doses are safe, and flag dangerous drug combinations. That's our **Live Scanner** page.

But how does the Cashier know the rules? Who wrote them?

**That's where the Admin Dashboard comes in.**

Think of the Admin Dashboard as the **Pharmacy Manager's Office**. This is where the rulebook is written and maintained. The manager has hired a very fast, very smart researcher (our AI) to go out, read thousands of medical documents, and bring back suggested rules.

But here's the key: **the manager never just automatically trusts the researcher.** Before any new rule goes into the official rulebook, the manager sits down, reviews the suggestions, fixes any mistakes, and decides exactly what gets saved — and what doesn't.

That process of *review → edit → approve* is exactly what the Admin Dashboard does.

---

## 2. A Simple Visual Map

```
                     ┌─────────────────────────────┐
                     │   👨‍💼  Admin Dashboard       │
                     │   (The Manager's Office)    │
                     └────────────┬────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼

  ┌───────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │ 🤖 Auto-Learner  │  │ 🗄️  Database     │  │ 🔬 Live Scanner  │
  │  (The Researcher) │  │ (Filing Cabinet) │  │  (The Front Desk)│
  │                   │  │                  │  │                  │
  │ • Reads FDA docs  │  │ Table 1:         │  │ • Scans real     │
  │ • Asks BioMistral │  │  Dosing Rules    │  │   prescriptions  │
  │   to extract data │  │                  │  │ • Checks the DB  │
  │ • Returns TWO     │  │ Table 2:         │  │   before flagging│
  │   lists of rules  │  │  Interactions    │  │   a patient risk │
  └───────────────────┘  └────────────────--┘  └──────────────────┘

  THE FLOW:
  Admin Dashboard asks Auto-Learner → Auto-Learner fetches rules
       → Admin Dashboard reviews rules → Admin approves
       → Database is updated → Live Scanner is now smarter
```

> **Key point to say out loud:** *"The Live Scanner and the Admin Dashboard both use the same database. The moment I approve a new rule here, the Live Scanner uses it immediately — no restart needed."*

---

## 3. Step-by-Step Workflow — The Story

> **Tell this as a story. Walk the judges through it one step at a time.**

---

### 📦 Step 1: The Delivery — The AI Brings Back New Rules

When the pharmacist types a drug name and clicks **"Fetch & Learn"**, our backend module called `auto_learner.py` wakes up and does the following:

1. It goes to the **official FDA website** (a public medical API) and downloads the drug's label — the same document that comes inside every medicine box.
2. It feeds that document to our **local AI model** (called BioMistral) and asks it to extract two things:
   - 📋 **Dosing Rules** — "What is the maximum safe daily dose for an adult? A child?"
   - ⚠️ **Drug Interactions** — "Which other drugs should NEVER be taken with this one?"

The AI sends back a structured response that looks like this:

```json
{
  "dosing_rules": [
    { "max_daily_dose_mg": 4000, "min_age_yrs": 18 }
  ],
  "known_interactions": [
    { "interacting_drug": "warfarin", "severity": "MAJOR",
      "reason": "Significantly increases bleeding risk." }
  ]
}
```

---

### 👀 Step 2: The Review — Showing the Rules Side-by-Side

Instead of saving those AI suggestions straight into the database, the dashboard **pauses and shows them to the human pharmacist first.**

The screen splits into two columns:

| 🟥 Left Column | 🟩 Right Column |
|---|---|
| The **current** rules already in the database | The **new** rules the AI just suggested |

This is like a "track changes" view in a Word document — *"here's what you have now, here's what the AI wants to change."*

Below the current rules, there are **two separate, clearly labelled sections**:
- **"Proposed Dosing Rules"** — shown as its own table
- **"Proposed Interactions"** — shown as a separate table underneath

They are displayed separately because they are stored in **two different database tables** and serve two completely different purposes in the safety engine.

---

### ✏️ Step 3: Human-in-the-Loop — The Pharmacist Can Fix AI Mistakes

This is one of the most important design decisions in the project. Explain it carefully.

**The AI is not perfect.** Sometimes it:
- Hallucates a dose that is too low or too high
- Copies a drug name with a typo
- Extracts a rule from the wrong section of the document

So instead of showing the tables as **read-only** displays, we used a Streamlit component called **`st.data_editor`**. This makes each table **fully editable** — like a mini Excel spreadsheet inside the web app.

The pharmacist can:
- ✏️ **Click any cell and correct a value** (e.g., change `400` mg to `4000` mg)
- ❌ **Delete an entire row** that looks wrong or hallucinated
- ➕ **Add a new row** manually if the AI missed something

> **Analogy for the judge:** *"It's like getting a first draft from a very fast intern. You wouldn't just publish it — you'd check it, fix the mistakes, and then sign off on the final version. That's exactly what this UI enforces."*

---

### ✅ Step 4: The Granular Save — Checkboxes for Selective Approval

This is the last, and most powerful, safety feature.

Imagine the AI got the **Interactions table perfectly right** but made a mistake in the **Dosing Rules**. In a simple system, you'd have to either approve everything or reject everything.

Our system is smarter. Below the editable tables, there are **two independent checkboxes**:

```
☑️  Overwrite Dosing Rules         ☑️  Append New Interactions
```

- If the pharmacist **only trusts the interactions data**, they uncheck "Dosing Rules" and click Approve.
- **Only the checked categories get saved.** The rest is ignored.

When **"Approve & Save Selected"** is clicked, the code does two completely independent things:

1. If "Dosing Rules" is checked → **deletes the old dosing rows** and **inserts the new edited ones** into the `advanced_dosing_rules` table
2. If "Interactions" is checked → **inserts the new pairs** into the `interactions` table (automatically skipping duplicates)

Then the page refreshes and the next conflict in the queue appears — until all pending reviews are resolved.

---

## 4. Why This Matters — 3 Talking Points for the Judge

> **Use these when the judge asks: "Why did you build it this way?"**

---

### 💡 Talking Point 1: Preventing AI Hallucinations from Reaching Patients

> *"An AI model — even a good one — can hallucinate. In most apps, that's inconvenient. In a pharmacy app, a wrong dose limit could harm a patient. Our Admin Dashboard is a mandatory human checkpoint. No AI-generated rule ever reaches the Live Scanner without a pharmacist reviewing and approving it first. We deliberately kept the AI out of the critical path for patient safety."*

---

### 💡 Talking Point 2: Granular Control, Not All-or-Nothing

> *"Most AI systems give you a binary choice — accept everything or reject everything. We rejected that approach. Our Granular Merge system lets the pharmacist save the good parts of an AI suggestion and discard the bad parts, independently. This is inspired by how professional software developers use code review — you approve specific changes, not entire files. We applied that same thinking to medical data."*

---

### 💡 Talking Point 3: Instant, System-Wide Effect on Patient Safety

> *"The moment a rule is approved here, it immediately protects the next patient. The Live Scanner reads from the same database in real time — there's no delay, no restart. If we just learned that Drug A and Drug B are a dangerous combination, the very next prescription scan will catch it. Every approval makes the whole system smarter, immediately."*

---

## 📝 Quick Reference — Key Terms for the Judge

| Term | What to say out loud |
|---|---|
| `auto_learner.py` | "Our background AI researcher — it fetches data so we don't have to type it manually." |
| `pharmacy.db` | "The filing cabinet — a local database storing all our safety rules." |
| `st.data_editor` | "An editable spreadsheet inside the web page — the key to human control." |
| `conflict_queue` | "A waiting list of drugs that need a human review before anything is saved." |
| `advanced_dosing_rules` | "Stores maximum safe doses — the Live Scanner checks every prescription against these." |
| `interactions` table | "Stores dangerous drug pairs — triggers an alert the moment two of them appear together." |
| `BioMistral` | "Our local medical AI model — runs completely offline, no patient data ever leaves the hospital." |

---

*Good luck with your presentation. You built something genuinely important.* 🎓
