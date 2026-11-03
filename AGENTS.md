# AFTERLIGHT contributor instructions

## Desktop-only product target

AFTERLIGHT is a **desktop-only** optimization and acceptance target, as explicitly
requested by the project owner.

- Prioritize impressive desktop interaction, clear desktop UX, keyboard/mouse
  camera controls, and measured desktop rendering performance.
- Do not spend time or resources optimizing for mobile or running mobile-specific
  acceptance tests unless the owner explicitly changes this direction.
- Preserve existing responsive behavior without expanding mobile work. Normal
  desktop window resizing and accessibility remain part of desktop quality.
- Keep default browser acceptance runs desktop-focused; any legacy mobile checks
  must remain optional rather than part of the default acceptance path.
