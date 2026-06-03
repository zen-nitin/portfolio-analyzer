interface Props {
  icon?: string
  title: string
  description?: string
}

export default function EmptyState({ icon = '○', title, description }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <p style={{ fontSize: '15px', fontWeight: 600, marginBottom: 4 }}>{title}</p>
      {description && <p style={{ fontSize: '13px' }}>{description}</p>}
    </div>
  )
}
