FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl gnupg lsb-release bash iputils-ping net-tools

# Replace apt-key usage with gpg --dearmor
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y docker-ce-cli

RUN mkdir -p /var/log/frr 
#RUN chown frr:frr /var/log/frr

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x ./scripts/apply_leak.sh

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
