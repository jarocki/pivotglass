# Pivotglass v0.8.5 UX redesign catalog

**Status:** implementation slice in progress

## Why this work exists

Pivotglass has accumulated the capabilities expected of a serious analyst
workbench, but the cockpit was making too many things look equally urgent. The
redesign preserves those capabilities while making the investigation path
obvious: start a pursuit, watch enrichment progress, inspect evidence, then
open analysis and reporting tools when they are needed.

## The first clarity slice

- The primary navigation now uses plain workflow labels: **Pursuit**, Dossier,
  **Charts & Evidence**, and **Service Status**.
- A persistent **Focus View** keeps the pursuit workspace dominant and tucks
  secondary charts, activity, attention, service meters, and decorative
  surfaces away. **Full Cockpit** restores the complete workspace.
- Opening a secondary pane automatically leaves Focus View, so an intentional
  navigation action never lands on a hidden surface.
- The command bar says **Command / Indicator** and uses a direct, plain-language
  placeholder while retaining the same command completion and keyboard routes.
- The Dossier and service meters use descriptive labels rather than theme-only
  metaphors.
- Assumptions, competing explanations, contradictions, and priority
  information requirements now open as progressive-disclosure sections in the
  Scientific Workbench. Their counts remain visible before expansion.
- A skip link, larger mobile targets, sticky command context, and a reduced
  mobile control set improve keyboard and small-screen flow.

## Preserved contracts

Existing pane IDs, URL routing, command completion, `/`, `F6`, `?`, Escape,
exports, evidence detail, and backend analytical state remain unchanged. Focus
View is presentation state only and is stored locally as
`pivotglass.focusView`. The first-use migration stores `pivotglass.uxVersion`
as `0.8.5` and starts Charts & Evidence collapsed so the initial screen has one
clear primary task.

## Next 0.8.5 slices

1. Move Activity & Errors and Attention Needed into a shared utility drawer.
2. Make the Dossier a contextual inspector on narrow screens.
3. Add a compact pursuit summary above the enrichment matrix and keep the full
   Scientific Workbench in the Analysis route.
4. Add contrast and keyboard walkthrough receipts for all themes at 320, 1024,
   and desktop widths.

The redesign is presentation-only: evidence, inference, narration, music, and
decorative theme elements remain visibly distinct.
