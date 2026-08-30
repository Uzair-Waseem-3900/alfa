# Requirements Document

## Introduction

The Cash Calculator is a purely frontend, client-side utility tool embedded within the AlphaPK ERP system. It enables users to count physical Pakistani currency — both notes and coins — by entering quantities per denomination. The tool computes a running total in real time, with no backend calls required. It is accessible to all authenticated user roles and is surfaced as a dedicated sidebar tab placed immediately after the existing "Ledger" entry in the main navigation.

## Glossary

- **Cash_Calculator**: The frontend page component located at `/cash-calculator` that renders the denomination input form and running total.
- **Denomination**: A specific face value of Pakistani currency, either a banknote or a coin (e.g., Rs. 5000, Rs. 1).
- **Quantity**: The non-negative integer count of physical notes or coins of a given denomination entered by the user.
- **Running_Total**: The computed sum of (denomination value × quantity) across all denominations, updated immediately on each input change.
- **Reset_Action**: A user-triggered action that clears all quantity fields back to blank (empty string), resulting in a Running_Total of zero.
- **Notes_Section**: The group of denomination input rows for Pakistani banknotes: Rs. 5000, Rs. 1000, Rs. 500, Rs. 100, Rs. 50, Rs. 20, Rs. 10 — rendered in that top-to-bottom order.
- **Coins_Section**: The group of denomination input rows for Pakistani coins: Rs. 5, Rs. 2, Rs. 1 — rendered in that top-to-bottom order below the Notes_Section.
- **Sidebar**: The persistent left-side navigation panel rendered by `Layout.jsx` containing `mainNavigation` links.
- **mainNavigation**: The array in `Layout.jsx` that defines top-level sidebar links rendered as direct `<Link>` items.
- **Layout**: The `Layout.jsx` component that wraps all authenticated pages and renders the Sidebar and main content area.
- **ProtectedRoute**: The route wrapper that ensures only authenticated users can access a given page.

---

## Requirements

### Requirement 1: Sidebar Navigation Entry

**User Story:** As an authenticated user of any role, I want to see a "Cash Calculator" link in the sidebar immediately after the "Ledger" entry, so that I can navigate to the tool from anywhere in the app.

#### Acceptance Criteria

1. THE `mainNavigation` array in `Layout.jsx` SHALL contain an entry with `name: 'Cash Calculator'`, `path: '/cash-calculator'`, and a currency-related icon, positioned immediately after the `{ name: 'Ledger', ... }` entry.
2. THE `mainNavigation` entry for Cash Calculator SHALL NOT include an `adminOnly` or `superuserOnly` restriction, making it visible to all authenticated roles.
3. WHEN a user navigates to `/cash-calculator`, THE Sidebar SHALL render the "Cash Calculator" link in an active/highlighted state using the `bg-primary-50 text-primary-700` style, consistent with other active mainNavigation links.
4. WHEN the sidebar is in collapsed mode (width `w-20`), THE Sidebar SHALL render the Cash Calculator entry as an icon-only link, consistent with the collapsed behavior of all other `mainNavigation` items.

---

### Requirement 2: Route Registration

**User Story:** As a developer, I want the `/cash-calculator` path registered in the application router, so that navigating to it renders the correct page component.

#### Acceptance Criteria

1. THE `App.jsx` router SHALL contain a `<Route path="/cash-calculator" ... />` entry that renders the `CashCalculatorPage` component wrapped in `<ProtectedRoute>` and `<Layout>`.
2. WHEN an unauthenticated user attempts to access `/cash-calculator`, THE `ProtectedRoute` SHALL redirect the user to `/login`, consistent with all other protected routes.

---

### Requirement 3: Denomination Input Fields

**User Story:** As a user counting physical cash, I want to enter a quantity for each denomination in a clearly labelled form, so that I can record how many notes and coins I have.

#### Acceptance Criteria

1. THE `Cash_Calculator` SHALL render a Notes_Section containing exactly seven denomination rows in top-to-bottom order: Rs. 5000, Rs. 1000, Rs. 500, Rs. 100, Rs. 50, Rs. 20, Rs. 10.
2. THE `Cash_Calculator` SHALL render a Coins_Section containing exactly three denomination rows in top-to-bottom order: Rs. 5, Rs. 2, Rs. 1.
3. THE `Cash_Calculator` SHALL render the Notes_Section above the Coins_Section.
4. WHEN the `Cash_Calculator` page first loads, THE `Cash_Calculator` SHALL display all denomination quantity inputs as blank (empty string), not zero.
5. THE `Cash_Calculator` SHALL accept only non-negative integer values in each denomination quantity input.
6. IF a user enters a non-numeric or negative value into a quantity input, THEN THE `Cash_Calculator` SHALL ignore the invalid portion and treat the field value as zero for calculation purposes without displaying an error message.

---

### Requirement 4: Real-Time Total Calculation

**User Story:** As a user counting cash, I want the grand total to update immediately as I type quantities, so that I always see the current sum without any manual action.

#### Acceptance Criteria

1. WHEN a user changes the quantity in any denomination input, THE `Cash_Calculator` SHALL recompute and display the Running_Total without requiring any button press.
2. THE `Cash_Calculator` SHALL compute the Running_Total as the sum of (denomination_value × quantity) for each denomination where quantity is a valid non-negative integer; blank or invalid fields SHALL contribute zero to the sum.
3. THE `Cash_Calculator` SHALL display the Running_Total formatted as Pakistani Rupees, using comma-separated thousands notation (e.g., `Rs. 1,23,500`).
4. WHEN all quantity inputs are blank or zero, THE `Cash_Calculator` SHALL display a Running_Total of `Rs. 0`.
5. THE `Cash_Calculator` SHALL display a per-row subtotal (denomination_value × quantity) alongside each denomination input row, updated in real time.

---

### Requirement 5: Reset Functionality

**User Story:** As a user who has finished counting or wants to start over, I want a Reset button that clears all fields instantly, so that I can begin a fresh count.

#### Acceptance Criteria

1. THE `Cash_Calculator` SHALL render a single Reset button visible at all times on the page.
2. WHEN a user activates the Reset button, THE `Cash_Calculator` SHALL set all denomination quantity inputs back to blank (empty string).
3. WHEN a user activates the Reset button, THE `Cash_Calculator` SHALL reset the Running_Total display to `Rs. 0`.
4. WHEN a user activates the Reset button, THE `Cash_Calculator` SHALL reset all per-row subtotals to blank or zero.

---

### Requirement 6: Visual Design and UI/UX

**User Story:** As a user, I want the Cash Calculator page to look and feel consistent with the rest of the ERP, so that the experience feels cohesive and professional.

#### Acceptance Criteria

1. THE `Cash_Calculator` page SHALL use Tailwind CSS utility classes consistent with the existing white/neutral palette (e.g., `bg-white`, `border-neutral-200`, `text-neutral-600`) and `primary-600` accent colours used across the app.
2. THE `Cash_Calculator` SHALL apply Framer Motion entrance animations to the page container and denomination rows, consistent with the animation patterns used in other ERP pages.
3. THE `Cash_Calculator` SHALL visually separate the Notes_Section and Coins_Section with a labelled divider or section heading.
4. THE `Cash_Calculator` SHALL display the Running_Total in a visually prominent, styled card or banner with larger text to distinguish it from the input rows.
5. THE `Cash_Calculator` denomination input rows SHALL each display the denomination label (e.g., "Rs. 5000"), a quantity input field, a multiplication indicator, and the per-row subtotal value.
6. THE Reset button SHALL be styled using the existing `Button` component from `../components/ui/Button`, or using equivalent Tailwind classes consistent with destructive/secondary action buttons in the ERP.
