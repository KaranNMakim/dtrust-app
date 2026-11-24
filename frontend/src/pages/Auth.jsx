import { SignIn, SignUp } from "@clerk/react";
import { ShieldCheck } from "lucide-react";

function Side() {
    return (<div className="hidden flex-1 flex-col justify-between border-r border-border bg-muted/60 p-12 lg:flex">
      <p className="text-base font-semibold">Decision Trust</p>
      <div className="max-w-md space-y-4">
        <h1 className="text-4xl font-semibold leading-tight">Why don&apos;t these two numbers agree, and which one should I trust?</h1>
        <p className="text-sm text-muted-foreground">
          See why two dashboards disagree, which number to trust, and fix it for good. Try it free on a sample company, no setup needed.
        </p>
        <ul className="space-y-2 text-sm">
          {["Free Acme demo: try every feature on a sample company", "Your own workspace, saved and private to you", "3 free credits to start on your own data"].map((t) => (<li key={t} className="flex items-start gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 text-primary"/>{t}</li>))}
        </ul>
      </div>
      <p className="text-xs text-muted-foreground">A credit score for enterprise knowledge.</p>
    </div>);
}

function Frame({ children }) {
    return (<div className="flex min-h-screen bg-background">
      <Side />
      <div className="flex flex-1 items-center justify-center p-6" data-testid="auth-panel">{children}</div>
    </div>);
}

export function SignInPage() {
    return <Frame><SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" withSignUp/></Frame>;
}

export function SignUpPage() {
    return <Frame><SignUp routing="path" path="/sign-up" signInUrl="/sign-in"/></Frame>;
}
