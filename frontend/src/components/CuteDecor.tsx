import { useTheme } from "../theme/ThemeProvider";
import sweetPinkBadgeUrl from "../assets/xhs-cat-pack/01.png";
import sweetPinkFloat02Url from "../assets/xhs-cat-pack/02.png";
import sweetPinkFloat03Url from "../assets/xhs-cat-pack/03.png";
import sweetPinkFloat04Url from "../assets/xhs-cat-pack/04.png";
import sweetPinkFloat05Url from "../assets/xhs-cat-pack/05.png";
import sweetPinkFloat06Url from "../assets/xhs-cat-pack/06.png";

export function CuteBrandIcon({ size = 38 }: { size?: number }) {
  const { theme } = useTheme();

  return theme === "sweetpink" ? (
    <img
      className="cute-brand-icon"
      src={sweetPinkBadgeUrl}
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
    />
  ) : null;
}

function SweetPinkCluster() {
  return (
    <div className="cute-sticker-cluster" aria-hidden="true">
      <img className="sweetpink-floating-item sweetpink-float sweetpink-float-main" src={sweetPinkFloat02Url} alt="" />
      <img className="sweetpink-floating-item sweetpink-float sweetpink-float-top" src={sweetPinkFloat03Url} alt="" />
      <img className="sweetpink-floating-item sweetpink-float sweetpink-float-left" src={sweetPinkFloat04Url} alt="" />
      <img className="sweetpink-floating-item sweetpink-float sweetpink-float-bottom" src={sweetPinkFloat05Url} alt="" />
      <img className="sweetpink-floating-item sweetpink-float sweetpink-float-side" src={sweetPinkFloat06Url} alt="" />
    </div>
  );
}

export function CuteStickerCluster() {
  const { theme } = useTheme();
  if (theme === "sweetpink") {
    return <SweetPinkCluster />;
  }
  return null;
}
