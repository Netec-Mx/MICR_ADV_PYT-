{{- define "msvc.pod" -}}
serviceAccountName: {{ .root.Values.name }}
automountServiceAccountToken: false
terminationGracePeriodSeconds: 30
securityContext:
  fsGroup: 10001
containers:
- name: {{ .root.Values.name }}
  image: {{ printf "%s@%s" .root.Values.image.repository (required "image.digest required" .digest) | quote }}
  imagePullPolicy: {{ .root.Values.image.pullPolicy }}
  command: ["python", "-m", "shared.vault.launcher", "--port", {{ .root.Values.port | quote }}]
  ports:
  - name: http
    containerPort: {{ .root.Values.port }}
  envFrom:
  - configMapRef:
      name: {{ .root.Values.name }}-config
  env:
  {{- range $key, $value := .root.Values.env }}
  - name: {{ $key }}
    value: {{ $value | quote }}
  {{- end }}
  {{- if .root.Values.mesh.enabled }}
  - name: LAB10_VARIANT
    value: {{ .variant | quote }}
  {{- end }}
  {{- if .extra }}
  - name: APP_VERSION
    value: {{ .root.Values.mesh.extra.appVersion | quote }}
  {{- end }}
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  resources:
    {{- toYaml .root.Values.resources | nindent 10 }}
  startupProbe:
    httpGet: {path: /health, port: http}
    periodSeconds: 5
    timeoutSeconds: 3
    failureThreshold: 60
  readinessProbe:
    httpGet: {path: /health, port: http}
    periodSeconds: 5
    timeoutSeconds: 3
    failureThreshold: 12
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    allowPrivilegeEscalation: false
    capabilities:
      drop: [ALL]
  volumeMounts:
  - name: vault-jwt
    mountPath: /var/run/secrets/vault
    readOnly: true
volumes:
- name: vault-jwt
  projected:
    defaultMode: 0440
    sources:
    - serviceAccountToken:
        path: token
        audience: vault
        expirationSeconds: 600
{{- end -}}
