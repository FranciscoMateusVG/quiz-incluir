import { SearchX } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { t } from "@/i18n/pt-BR";

export function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
      <SearchX className="size-16 text-muted-foreground" />
      <p className="text-5xl font-bold">404</p>
      <p className="text-lg text-muted-foreground">{t.pageNotFound}</p>
      <Button asChild>
        <Link to="/quizzes">{t.goToHomepage}</Link>
      </Button>
    </div>
  );
}
