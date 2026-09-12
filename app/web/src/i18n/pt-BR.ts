/**
 * UI strings in Brazilian Portuguese, per monorepo-incluir/AGENTS.md
 * ("Content/UI text must be in Brazilian Portuguese", "Error messages in
 * Portuguese"). The Flet original was entirely in English.
 *
 * Only the app *chrome* is translated. Quiz content — prompts, options,
 * reading passages, media captions — comes from the database and stays in
 * English, since that is the language being taught.
 *
 * A flat object rather than react-i18next: there is one locale, and this keeps
 * the strings greppable without adding a dependency or a provider.
 */
export const t = {
  appTitle: "Incluir Quiz",

  // picker
  welcomeBack: "Bem-vindo de volta",
  chooseQuiz: "Escolha seu próximo quiz",
  keepBuilding:
    "Continue desenvolvendo suas habilidades no idioma com sessões curtas de prática.",
  searchQuizzes: "Buscar quizzes",
  sectionReading: "Leitura",
  sectionListening: "Escuta",
  sectionVocabulary: "Vocabulário",
  questionsCount: (n: number) => `${n} ${n === 1 ? "questão" : "questões"}`,
  defaultQuizDescription: "Pratique vocabulário e gramática.",
  loadingQuizzes: "Carregando quizzes...",
  couldNotLoadQuizzes: "Não foi possível carregar os quizzes",
  noQuizzes: "Nenhum quiz disponível",
  noQuizzesHint: "Volte mais tarde para novos conteúdos.",
  noQuizzesMatch: "Nenhum quiz corresponde à sua busca",
  noQuizzesMatchHint: "Tente outra palavra-chave.",
  couldNotStartQuiz: "Não foi possível iniciar o quiz",
  quizHasNoQuestions: "Este quiz não tem questões.",

  // question
  questionProgress: (current: number, total: number) =>
    `Questão ${current} de ${total}`,
  back: "Voltar",
  next: "Próxima",
  finish: "Finalizar",
  yourAnswer: "Sua resposta",
  answerFirst: "Responda a questão primeiro.",
  couldNotSaveAnswer: "Não foi possível salvar sua resposta",
  unsupportedQuestionType: "Tipo de questão não suportado.",
  trueLabel: "Verdadeiro",
  falseLabel: "Falso",
  loadingQuiz: "Carregando quiz...",

  // results
  results: "Resultado",
  quizCompleted: "Quiz concluído!",
  percentCorrect: (pct: number) => `${pct}% de acerto`,
  takeAnotherQuiz: "Fazer outro quiz",
  downloadPdf: "Baixar PDF",
  couldNotDownloadReport: "Não foi possível baixar o relatório",

  // admin
  classGrades: "Notas da Turma",
  pickQuizForGrades:
    "Escolha um quiz para ver a distribuição de notas e o detalhamento por questão.",
  grades: "Notas",
  classLevel: "Turma (nível)",
  allLevels: "Todas as turmas",
  gradeDistribution: "Distribuição de notas",
  noFinishedAttempts: "Nenhuma tentativa finalizada para este filtro.",
  perQuestionBreakdown: "Acertos / erros por questão",
  colQuestion: "Questão",
  colCorrect: "Acertos",
  colWrong: "Erros",
  colUnanswered: "Sem resposta",
  autoUpdates: (seconds: number) =>
    `Atualiza automaticamente a cada ${seconds}s.`,
  loadingGrades: "Carregando notas...",
  couldNotLoadGrades: "Não foi possível carregar as notas",
  noAdminAccess: "Você não tem acesso ao painel administrativo.",
  score: "Nota",
  showTable: "Ver os números",
  colMin: "Mín",
  colMedian: "Mediana",
  colMax: "Máx",

  // media
  mediaUnavailable: "Mídia indisponível",
  openMedia: "Abrir mídia",

  // not found
  pageNotFound: "Página não encontrada",
  goToHomepage: "Ir para a página inicial",

  // login
  loginSubtitle: "Entre com sua conta do Programa Incluir",
  cpfLabel: "CPF",
  cpfPlaceholder: "Seu CPF",
  passwordLabel: "Senha",
  passwordPlaceholder: "Sua senha",
  signIn: "Entrar",
  signingIn: "Entrando...",
  loginFieldsRequired: "Informe seu CPF e sua senha.",
  loginAccountHint:
    "Sua conta é a mesma do Programa Incluir. Problemas para entrar? Fale com a coordenação.",
  loginErrorInvalidCredentials: "CPF ou senha inválidos.",
  loginErrorRateLimited: (seconds: number) =>
    `Muitas tentativas de login. Tente novamente em ${seconds}s.`,
  loginErrorRateLimitedGeneric:
    "Muitas tentativas de login. Tente novamente em instantes.",
  loginErrorServiceUnavailable:
    "O serviço de autenticação está indisponível no momento. Tente novamente em instantes.",
  loginErrorGeneric: "Não foi possível entrar. Tente novamente.",
  signOut: "Sair",
  adminGradesLink: "Admin: Notas",
} as const;
