import Editor from '@monaco-editor/react'
import './CodeEditor.css'

const DEFAULT_CODE = `// Paste your C source code here
// Example: the canonical PathGen test case

#include <stdio.h>

int classify_age(int age) {
    if (age >= 18) {
        printf("Adult\\n");
        return 1;
    } else {
        printf("Minor\\n");
        return 0;
    }
}

int main() {
    int age;
    scanf("%d", &age);
    classify_age(age);
    return 0;
}
`

const MONACO_LANGUAGE_MAP = {
  c: 'c',
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
}

export default function CodeEditor({ value, onChange, readOnly = false, language = 'c' }) {
  const monacoLanguage = MONACO_LANGUAGE_MAP[language] || 'c'

  return (
    <div className="code-editor">
      <Editor
        height="100%"
        language={monacoLanguage}
        value={value ?? DEFAULT_CODE}
        onChange={readOnly ? undefined : onChange}
        theme="vs-dark"
        options={{
          readOnly,
          fontSize: 13,
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontLigatures: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          lineNumbers: 'on',
          renderLineHighlight: 'gutter',
          padding: { top: 12, bottom: 12 },
          scrollbar: { verticalScrollbarSize: 5, horizontalScrollbarSize: 5 },
          bracketPairColorization: { enabled: true },
          suggest: { showKeywords: true },
          automaticLayout: true,
        }}
      />
    </div>
  )
}
