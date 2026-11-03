/** Native SVG implementation of the reviewed Canva route-intersection mark. */
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <img
      className={className}
      src={`${import.meta.env.BASE_URL}brand/mark.svg`}
      width="64"
      height="64"
      alt=""
      aria-hidden="true"
      draggable="false"
    />
  );
}
