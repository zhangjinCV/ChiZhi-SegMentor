import { useEffect, useState } from "react";

export function useImageElement(url?: string | null) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!url) {
      setImage(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const element = new Image();
    element.decoding = "async";
    element.onload = () => {
      if (!cancelled) {
        setImage(element);
        setError(null);
      }
    };
    element.onerror = () => {
      if (!cancelled) {
        setImage(null);
        setError("图片加载失败");
      }
    };
    element.src = url;
    return () => {
      cancelled = true;
      element.onload = null;
      element.onerror = null;
    };
  }, [url]);

  return { image, error };
}
