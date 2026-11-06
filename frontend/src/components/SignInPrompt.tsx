import { Link } from 'react-router-dom';
import { LogIn } from 'lucide-react';

export default function SignInPrompt({ what }: { what: string }) {
  return (
    <section className="panel empty-state">
      <LogIn size={32} aria-hidden />
      <h1>Sign in to {what}</h1>
      <p className="muted">Your saved places, route history and reports are tied to your account.</p>
      <Link className="primary-button" to="/profile">Sign in or create an account</Link>
    </section>
  );
}
