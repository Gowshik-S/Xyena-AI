---
name: Xyena Delivery
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#45464d'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#505f76'
  on-secondary: '#ffffff'
  secondary-container: '#d0e1fb'
  on-secondary-container: '#54647a'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#271901'
  on-tertiary-container: '#98805d'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#fcdeb5'
  tertiary-fixed-dim: '#dec29a'
  on-tertiary-fixed: '#271901'
  on-tertiary-fixed-variant: '#574425'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  mono-data:
    fontFamily: monospace
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 24px
  gutter-table: 12px
  row-height-dense: 32px
  row-height-standard: 48px
---

## Brand & Style

The design system is engineered for **Xyena Delivery**, a B2B logistics platform where precision, auditability, and data density are paramount. The brand personality is authoritative, systematic, and immutable. 

The aesthetic follows a **Corporate / Modern** direction with a heavy emphasis on **Information Density**. It draws inspiration from high-end ERP systems, prioritizing functional utility over decorative flair. The interface should feel like a professional tool—stable, predictable, and highly efficient for power users managing complex global supply chains.

**Key Principles:**
- **Data Integrity:** Visual cues must emphasize the "Immutable Logistics Audit" nature of the product.
- **High Information Density:** Maximum data visibility with minimal scrolling.
- **Systematic Order:** Rigorous alignment and consistent modularity to reduce cognitive load in high-stress environments.

## Colors

The palette is anchored by **Deep Navy (#0F172A)**, providing a high-contrast foundation that evokes institutional trust. The system utilizes a semantic color model to provide immediate status recognition across global shipments.

- **Primary (Slate 900):** Used for navigation, primary actions, and core structural elements.
- **Surface & Backgrounds:** The main workspace uses a very light gray (#F8FAFC) to reduce eye strain, while borders use a crisp #E2E8F0 to define tabular structures.
- **Status Tiers:**
    - **Success (Emerald):** Indicates terminal positive states like "Delivered."
    - **Warning (Amber):** Highlights "Exceptions" or "Mismatches" requiring attention but not immediate stoppage.
    - **Error (Rose):** Flags "Rejected" or "Failed" audits.
    - **Info (Blue):** Tracks active "In-Transit" states.

## Typography

The design system utilizes **Inter** for its exceptional legibility in small sizes and its neutral, professional tone. 

**Usage Guidelines:**
- **Tabular Data:** Use `body-sm` for standard table rows to maximize vertical density.
- **Metadata:** Use `label-md` for column headers and section labels, always in uppercase with increased tracking to differentiate from interactive data.
- **Identifiers:** Tracking numbers, SKUs, and Hash IDs should use a monospaced font at the `mono-data` level to ensure character clarity (distinguishing between '0' and 'O').
- **Scalability:** For mobile views, `headline-lg` should scale down to 20px (`headline-md`) to ensure dashboard titles remain visible on smaller viewports.

## Layout & Spacing

This design system employs a **Fixed-Fluid Hybrid Grid**. The sidebar navigation remains fixed at 240px, while the main content area utilizes a fluid 12-column grid.

**Layout Philosophy:**
- **Density:** We utilize a 4px base unit. Component internal padding is kept tight (8px to 12px) to support data-heavy ERP workflows.
- **The Audit View:** Central to the layout is a multi-pane split view. A left-hand list of shipments (320px-400px) controls a detailed right-hand audit pane.
- **Breakpoints:**
    - **Desktop (1280px+):** Full 12-column display with expanded data tables.
    - **Tablet (768px - 1279px):** Sidebar collapses to icons; tables transition to a horizontal scroll or card-based view.
    - **Mobile (<768px):** Single column focus; priority given to Exception Banners and status updates.

## Elevation & Depth

To maintain a "flat and functional" professional feel, this design system avoids heavy shadows. Depth is communicated through **Tonal Layers** and **Low-contrast Outlines**.

- **Level 0 (Background):** #F8FAFC (Neutral Slate).
- **Level 1 (Cards/Containers):** Pure white (#FFFFFF) with a 1px border (#E2E8F0). No shadow.
- **Level 2 (Dropdowns/Modals):** Pure white with a 1px border and a subtle, high-diffusion shadow (0px 4px 12px rgba(15, 23, 42, 0.08)) to indicate interactivity and temporary state.
- **Level 3 (Popovers):** Used for tooltips or data-point details, featuring a dark background (#0F172A) to contrast sharply against the light UI.

## Shapes

The shape language is **Soft (0.25rem)**. This slight rounding provides a modern feel while maintaining the rigid, structural integrity required by an enterprise application.

- **Buttons & Inputs:** 4px (0.25rem) corner radius.
- **Cards & Banners:** 8px (0.5rem) corner radius.
- **Status Badges:** 2px or fully square to differentiate them from interactive buttons.
- **Data Visualizations:** Progress bars and quantity widgets should use square ends to reinforce the "block" nature of logistics units (containers, pallets).

## Components

### High-Density Tables
Tables are the core of the design system. They must feature `sticky` headers, zebra-striping on hover, and inline editing capabilities. Cell padding is restricted to 8px horizontally.

### Status Badges
Badges use a "Subtle Fill" approach: a 10% opacity background of the semantic color with 100% opacity text. This prevents "color fatigue" while maintaining clear categorization.

### Immutable Timelines
A vertical stepper component used for the "Audit Trail." Completed steps are marked with a solid Primary color dot; current steps use a pulse effect; exceptions use the Error/Warning icons.

### Quantity Comparison Widgets
Horizontal progress bars used within table cells to show "Expected vs. Received" quantities. Mismatches are highlighted by changing the remaining bar segment to the Warning (Amber) color.

### Exception Banners
Placed at the top of detail views. These use a solid left-border (4px) in the Error or Warning color, with a light tinted background to ensure they are the first thing a user sees upon page load.

### Input Fields
Inputs use a white background with a 1px #CBD5E1 border. On focus, the border shifts to Primary Navy with a 2px outer "halo" of 10% Primary color.