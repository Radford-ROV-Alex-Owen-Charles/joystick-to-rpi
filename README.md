# Joystick to Raspberry Pi Project

This project enables joystick inputs from a computer to be sent to a Raspberry Pi 4 over Ethernet. It consists of a client application that reads joystick inputs and a server application that receives these inputs and controls motors on the Raspberry Pi.

## Project Structure

```
joystick-to-rpi
├── src
│   ├── client
│   │   ├── __init__.py
│   │   ├── joystick_reader.py
│   │   └── network_client.py
│   ├── server
│   │   ├── __init__.py
│   │   ├── network_server.py
│   │   └── motor_controller.py
│   ├── common
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   └── protocol.py
│   └── utils
│       ├── __init__.py
│       └── logging_utils.py
├── config
│   ├── client_config.json
│   └── server_config.json
├── scripts
│   ├── start_client.py
│   └── start_server.py
├── tests
│   ├── __init__.py
│   ├── test_joystick_reader.py
│   └── test_network.py
├── requirements.txt
└── README.md
```

## Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd joystick-to-rpi
   ```

2. **Install Dependencies**
   Ensure you have Python installed, then install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Client and Server**
   Edit the `config/client_config.json` and `config/server_config.json` files to set the appropriate IP addresses and ports.

4. **Run the Server**
   Start the server on the Raspberry Pi:
   ```bash
   python scripts/start_server.py
   ```

5. **Run the Client**
   Start the client on your computer:
   ```bash
   python scripts/start_client.py
   ```

## Usage

- The client will read joystick inputs and send them to the server.
- The server will receive the inputs and control the motors based on the received data.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.