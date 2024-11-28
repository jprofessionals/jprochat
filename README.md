Setup:
```
sudo sh -c 'echo "export AWS_DEFAULT_REGION=eu-west-1" >>/etc/environment'
sudo apt-get update
sudo apt-get upgrade
sudo apt -y install python3-pip
sudo apt install python3.12-venv
python3 -m venv chat3
source chat3/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
echo 'deb https://debian.neo4j.com stable latest' | sudo tee -a /etc/apt/sources.list.d/neo4j.list
sudo add-apt-repository universe
sudo apt-get update
sudo apt-get install neo4j=1:5.20.0
sudo apt install openjdk-17-jre
sudo apt remove openjdk-19-jre-headless
sudo neo4j-admin dbms set-initial-password Neo4jSecretpw
sudo systemctl enable neo4j

sudo vi /etc/neo4j/neo4j.conf
- enable line with: server.default_listen_address=0.0.0.0 # only if neo should be available outside the server!
- add line: dbms.security.procedures.unrestricted=algo.*,apoc.*

sudo cp /var/lib/neo4j/labs/apoc-5.20.0-core.jar /var/lib/neo4j/plugins/
sudo systemctl start neo4j

sudo apt-get update
sudo apt-get install software-properties-common
sudo add-apt-repository ppa:canonical-chromium-builds/stage
sudo apt-get update
sudo apt-get install chromium-browser
sudo apt-get install xdg-utils

make sure the machines IP adress is whitelisted in cloudflare
on Security → WAF → Tools → IP Access Rules for the jpro.no site

mkdir CV

crontab -e and add the following lines:
10 03 * * * cd /home/ubuntu && source chat3/bin/activate && python3 fetcharticles.py
31 03 * * 1 cd /home/ubuntu && source chat3/bin/activate && python3 fetchCVs.py

sudo cp jprochat.service /etc/systemd/system/jprochat.service
sudo systemctl daemon-reload
sudo service jprochat start

```
