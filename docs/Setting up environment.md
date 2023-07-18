## Setting up local environment

### Prerequisites

WSL2 is required to run the project locally. You can follow the
instructions [here](https://learn.microsoft.com/en-us/windows/wsl/install) to install WSL2 on your machine.

### Installation

1. Clone the repository

```sh
git clone https://github.com/Jake55111/MarketEngine 
```

2. Set up and activate the virtual environment

```sh
python3 -m venv venv
```

```sh
source venv/bin/activate
```

4. Install the dependencies

```sh
pip install -r requirements.txt
```

5. Install redis

```sh
sudo apt install redis
```

6. Install and configure MySQL

```sh
sudo apt install mysql-server
```

```sh
sudo systemctl start mysql.service
```

```sh
sudo mysql
```

```sh
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'password';
```

```sh
exit
```

```sh
sudo mysql_secure_installation
```

```sh
mysql -u root -p
```

```sh
ALTER USER 'root'@'localhost' IDENTIFIED WITH auth_socket;
```

```sh
CREATE USER 'market'@'localhost' IDENTIFIED BY 'password';
```

```sh
GRANT ALL PRIVILEGES ON *.* TO 'market'@'localhost';
```

```sh
FLUSH PRIVILEGES;
```

```sh
CREATE DATABASE market;
```

```sh
exit
```


