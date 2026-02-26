# Server Plan 07: User Dashboard (Demo Consumer Experience)

*Spec reference: Section 5.2*

## Purpose

A simple React-based web application that demonstrates the consumer experience of the Newshare Network. It shows users their current session, which publishers they've visited, their account balance, and privacy controls. This directly implements the "user queries their clickstream" feature described in the original Clickshare patent.

For the pilot, this is a **demo/proof-of-concept**, not a full production application. Its purpose is to make the network tangible for funders, publishers, and test users.

## Core Responsibilities

- Display user's current session information (home base, subscription tier)
- Show publishers the user has visited (from their clickstream at their home base)
- Display account balance and transaction history
- Privacy controls: view/revoke data sharing preferences
- Demonstrate the user empowerment promise of the Newshare Network

## Technology Stack (from spec Section 5.2)

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Frontend** | React 19 + TypeScript | Spec explicitly recommends React |
| **Build Tool** | Vite | Fast development, modern bundling |
| **Styling** | Tailwind CSS 4 | Rapid UI development |
| **Auth** | OIDC client (via home base) | User logs in through their home base |
| **Data** | REST API calls to home base profile store | User's own data |
| **Hosting** | Same cloud VM (static files via Nginx) or Vercel/Cloudflare Pages | Minimal infrastructure |

## Key Views

```
/dashboard         → Session overview, subscription status, recent activity
/publishers        → List of publishers visited, per-publisher pseudonymous ID status
/transactions      → Content accessed, charges, balance
/privacy           → Privacy level setting, data sharing controls, "disappear" button
/account           → Profile, preferences (adPreference, doNotTrack, etc.)
```

## Implementation Steps

### Phase 1: Core Dashboard (Weeks 1-3)
1. Scaffold React app with Vite + TypeScript + Tailwind
2. Implement OIDC login flow (authenticate through home base)
3. Build dashboard view: current session, subscription tier, home base info
4. Build publisher list: which publishers the user has visited
5. Build transaction view: content accessed, wholesale/retail pricing breakdown

### Phase 2: Privacy Controls (Weeks 3-5)
6. Build privacy preferences UI (privacyLevel, adPreference, doNotTrack)
7. Implement "disappear" from publisher: trigger PPID unlinking at home base
8. Show what data is shared with each publisher (based on privacyLevel)
9. Build data export request functionality

### Phase 3: Pilot Polish (Weeks 5-6)
10. Mobile-responsive design for phone/tablet users
11. Demo mode: pre-populated with sample data for funder presentations
12. Deploy on pilot infrastructure
13. User testing with pilot participants

## Infrastructure Requirements

- **Compute:** Static files served via Nginx (nearly zero additional compute)
- **Storage:** < 100MB of static assets
- **Network:** Publicly accessible HTTPS
- **API Backend:** Home base provides all user data — no separate backend needed

## Interfaces

- **Home Base** provides user profile, clickstream, balance, privacy controls via API
- **Users** interact via web browser
- **Funders/stakeholders** view demos of the consumer experience
