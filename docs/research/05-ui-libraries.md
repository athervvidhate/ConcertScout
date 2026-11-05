# 05 - UI libraries and design guidance for the Concert Scout overhaul

Research date: 2026-11-04. Method: each URL was fetched with WebFetch (summarised by a small model, so figures are as reported, not independently re-checked), plus the linked GitHub repos where the site was thin. Anything not seen is marked UNVERIFIED.

## Bottom line

Use a small, mostly-rules-driven combination, not a big component kit:

1. **coss ui** (Base UI primitives, copy-paste, Tailwind) as the component base: Input, Input Group, Combobox/Autocomplete, Composer, Toggle Group, Progress, Badge, Drawer. Base UI is the actively maintained successor to Radix-style primitives and the library ships the source into the repo. Confirm its Tailwind 4 and install command on /ui/docs before committing (not shown on the pages read).
2. **Emil Kowalski's rules plus the ui-skills Playbook** as the written design contract (motion budget, no-animate cases, typography, contrast, focus). Install the `ui-skills` skills (MIT) so the coding agent applies them.
3. **ReUI** only as a reference or copy source for the editable-filter-chip pattern (its Filters set, shadcn CLI, MIT). Note it follows Radix for most components, so mixing it with coss means two primitive families. Prefer copying the idea, not the dependency.
4. Skip React Bits for the product UI (heavy, decorative, licence caveat). BoardUI is a useful agent-progress reference but React Aria based and partly paid. The Design System Checklist is a planning aid only.

The default motion position: almost nothing animates. Only streamed-step reveal, popovers, and toasts get motion, all under 300ms, ease-out, via CSS transitions. No Motion library needed.

## Per-resource findings

### 1. BoardUI - https://www.boardui.com/ , https://github.com/boardui/boardui
- **What:** React design system for dashboards and agentic interfaces. Page claims 103 components (19 charts), 10 Pro templates, 400+ tokens, Figma design.
- **Install:** own CLI `npx boardui@latest add <component>` (`list`, `add --all`), and an MCP server (`claude mcp add boardui -- npx -y boardui@latest mcp`). Not the shadcn registry.
- **Stack:** React 19.2, Tailwind v4, **React Aria** v1.17, TanStack Table v8.21. Neither Radix nor Base UI. Motion not mentioned.
- **Licence/cost:** Free tier (69 items) MIT in public repo. Pro is paid one-time: EUR 149 (1 yr updates), 199 (lifetime), 349 (startups, 5 users).
- **Maintenance:** repo 975 stars, 49 commits, takes no PRs; last-commit date not shown (UNVERIFIED). Pro launch banner has no date.
- **Useful:** agent-oriented items: Composer attachments, Web search, Agent progress, Agent thinking, Composer loader (names from the page; whether free or Pro is UNVERIFIED), Data table, AI Chat template.
- **Avoid:** adopting a third primitive family (React Aria) alongside the rest; Pro lock-in; single-maintainer, no-PR repo.

### 2. React Bits - https://reactbits.dev/ , https://github.com/DavidHDev/react-bits
- **What:** library of animated React components and backgrounds: Text Animations, Animations, Components, Backgrounds, Micro Interactions. JS/TS and CSS/Tailwind variants.
- **Install:** shadcn CLI (`npx shadcn@latest add @react-bits/SplitText-TS-TW`), jsrepo, manual copy, MCP.
- **Stack:** repo package.json (the demo site's, not per component) includes motion ^12, gsap ^3.13, three ^0.180, ogl, @react-three/*, lenis, matter-js, Tailwind ^4. Individual components pull a subset; which ones is UNVERIFIED.
- **Licence/cost:** "MIT + Commons Clause", free for personal and commercial use per repo page; full LICENSE.md text not read, so Commons Clause terms UNVERIFIED. A "Pro" nav link exists; contents/price UNVERIFIED.
- **Maintenance:** 51.3k stars, 1,687 commits; last-commit date not shown.
- **Useful for us:** nearly nothing. At most a restrained text reveal for the streamed progress label.
- **Avoid:** WebGL/shader backgrounds (Aurora-style, particles), split-text hero effects, cursor followers, gradient blobs. These are the canonical AI-slop look and cost GPU, battery, and LCP. Also a motion-sickness and `prefers-reduced-motion` risk.

### 3. UI Skills - https://ui-skills.com , https://github.com/ibelick/ui-skills , https://www.ui-skills.com/playbook
- **What:** catalog of 20 agent skills for design engineering plus a Playbook of distilled UI rules. Repo MIT, 10.4k+ stars (site), 503 commits.
- **Install:** `npx ui-skills start`, `npx ui-skills list --category motion`, `npx ui-skills get baseline-ui`; MCP endpoint https://www.ui-skills.com/mcp (tools `list_skills`, `get_skill`). Works with Claude Code, Cursor, Codex, Copilot, OpenCode.
- **Skills relevant to us (descriptions only; skill bodies UNVERIFIED, `/skills/baseline-ui` URL returned 404):** `improve-ui` (read-only audit), `improve-animations` (emilkowalski, read-only motion audit), `better-ui` (jakubkrehel: hover, shadows, borders, enter/exit, radius, optical alignment), `impeccable` (pbakaus, anti-generic craft), `frontend-design` (anthropics, already installed locally), `interface-design` (dashboards), `improve-react`. Skip: stopmotion-video, reanimate, fun-isometric, figma-designer, gpt-tasteskill (GSAP-oriented).
- **Recommendation:** install `improve-animations`, `better-ui`, `improve-ui`, plus `baseline-ui` (named in README CLI example; contents UNVERIFIED). Read each skill body before committing it, since third-party skill text becomes agent instructions.
- **Playbook rules read in full** are in the rules section below.

### 4. coss ui - https://coss.com/ui , https://github.com/cosscom/ui , https://coss.com/ui/docs
- **What:** "modern UI component library built on top of Base UI", designed to be LLM-readable. Copy-paste-and-own. Docs list a Skills page and llms.txt (contents UNVERIFIED).
- **Install:** copy-paste model confirmed; exact CLI/registry command UNVERIFIED (docs "Get Started" not captured).
- **Stack:** **Base UI** (not Radix), Tailwind CSS (version UNVERIFIED). Motion dependency not mentioned (UNVERIFIED). Includes legacy Origin UI components and "Particles" blocks.
- **Licence/cost:** repo says whole repository MIT. Free.
- **Maintenance:** 10.8k stars, 1,163 commits, 2026 copyright, "New" badge on Composer. Last-commit date not shown.
- **Components seen:** Autocomplete, Combobox, Composer, Input, Input Group, Number Field, Segmented Control, Select, Slider, Switch, Textarea, Toggle Group, Progress, Meter, Calendar, Date Picker, Drawer, Menu, Table, Badge. No dedicated chips/tags, steps, list, or map component.
- **Useful:** Composer or Input Group for the query box; Combobox for filter value pickers; Toggle Group/Segmented Control for sort and view; Progress for the search bar; Badge as chip base.
- **Gaps:** removable/editable chip, stepper/timeline for streamed steps, ranked list row, map. Build these ourselves (small).

### 5. Design System Checklist - https://designsystemchecklist.com , https://github.com/ardakaracizmeli/design-system-checklist
- **What:** open-source checklist for planning, building, growing a design system. Next.js site, 505 stars, 113 commits; languages EN/ES/KO/PT/TR/ZH.
- **Content:** the checklist items themselves were not retrievable (site shell only), so specific items are UNVERIFIED. Licence not stated (no LICENSE file seen).
- **Use:** low value for us. Treat as a prompt for defining tokens (colour, type scale, spacing, radius, states) once; not a source of rules.

### 6. ReUI - https://reui.io/components
- **What:** free catalog of 1,264+ shadcn/ui-based components plus paid Pro blocks.
- **Install:** shadcn CLI `npx shadcn@latest add ...`; no npm package, source copied into the repo.
- **Stack:** Radix for standard components; 22 in-house components in both Radix and Base UI (`@base-ui/react`) variants. Tailwind version UNVERIFIED. Chart is "motion-powered" (version unknown).
- **Licence/cost:** MIT (per FAQ); Pro from $249 one-time.
- **Maintenance:** ~3.9k stars, public roadmap, 2026 copyright; no version or commit dates seen.
- **Useful:** Filters (12, schema-driven, URL state via nuqs) is the closest fit to editable filter chips and URL-synced state; Badge (25) for chips; Stepper (44) and Timeline for step progress; Data Grid/Table for ranked rows (TanStack). No free map (fleet dispatch map is Pro only).
- **Avoid:** Pro-only blocks, the large Data Grid when we have a simple ranked list, and mixing Radix and Base UI trees.

### 7. Emil Kowalski, "You don't need animations" - https://emilkowal.ski/ui/you-dont-need-animations
Fully read. Points:
- Animate with purpose: explain a feature, give feedback, smooth a state change, or (rarely seen only) delight.
- Frequency decides: things used hundreds of times a day (Raycast) are best with no animation. Hover effects on daily-use elements benefit from none.
- **Never animate keyboard-initiated actions** (a highlight lagging arrow-key list navigation feels broken).
- Speed: UI animations under about 300ms; a 180ms dropdown feels more responsive than 400ms.
- Tooltips: slight initial delay, then no delay and no animation when moving to the next tooltip.
- Delight-only animation becomes irritating in frequently used components.
- The article gives no easing curves; those come from the Playbook below.

## Rules worth adopting (concrete)

Motion
1. No animation on keyboard-driven actions: arrow-key focus in result rows, chip delete via Backspace, Enter to search, tab switches (Emil; Playbook "keep tab switches instant").
2. Budget: under 300ms, `ease-out` for entrances and feedback, no springs on toggles and toasts (Playbook).
3. Entrances start near 95% scale, never from zero; exits short with a small translateY or plain fade (Playbook).
4. Use CSS transitions for open/close states so they are interruptible; no Motion library for this app (Playbook).
5. Press feedback: `:active` scale about 0.96 on buttons only (Playbook).
6. Stagger only first-load hero, about 100ms; never for repeated actions such as each streamed step (Playbook). For streamed steps: fade a new row in once, no stagger, no typewriter.
7. Always honour `prefers-reduced-motion` (standard practice; not stated in the pages read).

Accessibility and forms
8. 44x44px touch targets; `:focus-visible` rings; visible labels, never placeholder-only; inline field errors; status never by colour alone (Playbook). Chips need a text or icon state and an accessible remove button name.
9. Muted text must keep sufficient contrast (Playbook; ratio number UNVERIFIED).

Typography and layout
10. `text-balance` headings, `text-pretty` body, `tabular-nums` for dates, distances, ranks, and prices; sentence case labels; 60 to 75 character lines.
11. Concentric radius (child radius = parent radius minus padding); spacing before divider lines; shadows for depth, borders for structure.
12. Reserve space with `aspect-ratio` (map and images) so the layout does not jump while the map loads.
13. Skeletons that match the result rows instead of spinners; empty state with exactly one action; confirm destructive actions.
14. One accent colour per view; neutral headings; no glow on primary buttons; solid modal scrims instead of blur.
15. Fade truncated venue or artist names rather than hard ellipsis; scroll-edge `mask-image` fade on the result list.

## Mapping to our product

| Element | Take | Avoid |
|---|---|---|
| Query input | coss Composer or Input Group, visible label or clear aria-label, Enter submits with no animation | animated gradient borders, glowing "AI" input, sparkle icons |
| Editable filter chips | coss Badge + Toggle Group/Combobox; ReUI Filters as pattern reference; remove button with accessible name; instant keyboard handling | chip enter/exit springs, drag-jiggle |
| Streamed progress steps | coss Progress for overall; plain list with one fade-in per step, icon plus text state (pending, active, done), `tabular-nums` timers | shimmer text on every step, typewriter streaming, pulsing orbs, fake "thinking" blobs |
| Ranked result rows | plain semantic list, `tabular-nums` rank and distance, hover with no animation, spacing over dividers | card tilt/3D hover, staggered re-ordering animation on every filter change, gradient score badges |
| Map | reserve aspect-ratio box, lazy-load the map library, static fallback; no map component exists in coss or free ReUI (build or choose separately; map library choice is outside these sources) | decorative WebGL/globe effects, heavy blur overlays, animating markers continuously |

## What to avoid overall (slop and cost)
- WebGL, shader, particle, aurora, and grain backgrounds (React Bits style): GPU cost, LCP, battery.
- Blur/glass panels and full-screen backdrop blur (Playbook: expensive full-screen rendering).
- Glows, purple-to-blue gradients, sparkle icons, shimmering text, bouncy springs.
- Animating anything keyboard-driven or high-frequency.
- Mixing three primitive families (Radix, Base UI, React Aria); pick Base UI.
- Installing third-party skills or registries blind: read the source first.

## Unverified summary
- coss: exact install command, Tailwind version, motion dependency, skills page content.
- React Bits: Commons Clause text, per-component dependencies, Pro contents.
- BoardUI: which agent components are free; last-commit date.
- ui-skills: individual skill bodies (baseline-ui URL 404), improve-animations rules.
- Design System Checklist: all checklist items, licence.
- ReUI: Tailwind version, commit dates.
