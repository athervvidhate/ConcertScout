// Run before paint so a stored choice never flashes the opposite palette.
export const THEME_BOOT = `(function(){try{var m=localStorage.getItem('concert-scout-mode');document.documentElement.dataset.mode=m==='light'||m==='dark'?m:matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}catch{document.documentElement.dataset.mode=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}})()`;

export function toggleTheme() {
  const mode =
    document.documentElement.dataset.mode === "dark" ? "light" : "dark";
  const apply = () => {
    document.documentElement.dataset.mode = mode;
  };
  if (
    !matchMedia("(prefers-reduced-motion: reduce)").matches &&
    document.startViewTransition
  )
    document.startViewTransition(apply);
  else apply();
  try {
    localStorage.setItem("concert-scout-mode", mode);
  } catch {
    /* Still works for this visit. */
  }
}
