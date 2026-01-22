# Review Questions

- Do we need to support Safari private mode explicitly? If yes, I will add guarded `localStorage` access and fallbacks.
- Should delete actions be POST-only (instead of links) for consistency and to avoid accidental navigation?

# Review Findings

- Invalid table/form nesting can break submit behavior in Safari/Edge/Chrome (forms must not be direct children of `tr`), so modify actions may silently fail or submit wrong fields. `src/safe_family/templates/rules/suspicious_view.html:92`.
- Buttons wrapping anchors inside a form can trigger unexpected submits or ignore the link click in different browsers; delete actions may submit the modify form instead. `src/safe_family/templates/rules/suspicious_view.html:106`, `src/safe_family/templates/rules/suspicious_view.html:239`, `src/safe_family/templates/auth/register.html:20`.
- Unprotected `localStorage` calls can throw in Safari private mode and abort scripts, which may break modal flows and updates. `src/safe_family/static/js/todo.js:401`, `src/safe_family/static/js/todo.js:431`.
- Username autocomplete uses `given-name`, which blocks standard password manager autofill in Chrome/Edge/Safari. `src/safe_family/templates/auth/login.html:9`.
- Duplicate `type` attribute on a hidden date input is invalid HTML and can render inconsistently. `src/safe_family/templates/rules/suspicious_view.html:75`.
- `target="_blank"` without `rel="noopener noreferrer"` is a security footgun and can undermine user trust. `src/safe_family/templates/rules/suspicious_view.html:36`.
