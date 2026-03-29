import { Highlight, themes } from 'prism-react-renderer'

type Props = {
  code: string
  variant: 'light' | 'dark'
}

/**
 * Syntax-highlighted JSON for the graph inspector (Prism: keys, strings, numbers, booleans, punctuation).
 */
export function JsonInspectorPre({ code, variant }: Props) {
  const prismTheme = variant === 'dark' ? themes.vsDark : themes.github

  return (
    <div className="inspector-json-scroll">
      <Highlight theme={prismTheme} code={code} language="json">
        {({ className, style, tokens, getLineProps, getTokenProps }) => (
          <pre
            className={`${className} inspector-json-pre-inner`}
            style={{
              ...style,
              margin: 0,
            }}
          >
            {tokens.map((line, lineIndex) => {
              const lineProps = getLineProps({ line })
              return (
                <span
                  key={lineIndex}
                  {...lineProps}
                  style={{
                    ...lineProps.style,
                    display: 'block',
                    minHeight: '1.35em',
                  }}
                >
                  {line.map((token, tokenIndex) => (
                    <span key={tokenIndex} {...getTokenProps({ token })} />
                  ))}
                </span>
              )
            })}
          </pre>
        )}
      </Highlight>
    </div>
  )
}
