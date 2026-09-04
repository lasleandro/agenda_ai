export function LandingRequestCta({
  className,
  withArrow = false,
}: {
  className?: string;
  withArrow?: boolean;
}) {
  return (
    <a className={className} href="/solicitar-conta">
      Solicitar uma conta
      {withArrow && <span aria-hidden="true">&rarr;</span>}
    </a>
  );
}

