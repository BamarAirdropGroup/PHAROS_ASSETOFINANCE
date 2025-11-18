
import os
import re
import asyncio
import random
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

import pytz
from colorama import Fore, Style, init as colorama_init
from aiohttp import ClientSession, ClientTimeout, BasicAuth, ClientResponseError
from aiohttp_socks import ProxyConnector
from eth_account import Account
from eth_utils import to_checksum_address
from web3 import Web3
from web3.exceptions import TransactionNotFound


colorama_init(autoreset=True)

wib = pytz.timezone("Asia/Jakarta")


class AssetoFinance:
    def __init__(self) -> None:
        
        self.RPC_URL = "https://atlantic.dplabs-internal.com/"
        self.EXPLORER = "https://atlantic.pharosscan.xyz/tx/"
        self.USDT_CONTRACT_ADDRESS = "0xE7E84B8B4f39C507499c40B4ac199B050e2882d5"
        self.CASH_CONTRACT_ADDRESS = "0x56f4add11d723412D27A9e9433315401B351d6E3"
        self.CONTRACT_ABI = [
            {
                "inputs": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "address", "name": "spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "spender", "type": "address"},
                    {"internalType": "uint256", "name": "value", "type": "uint256"},
                ],
                "name": "approve",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function",
            },
            {
                "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "uAddress", "type": "address"},
                    {"internalType": "uint256", "name": "tokenAmount", "type": "uint256"},
                ],
                "name": "redemption",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "uAddress", "type": "address"},
                    {"internalType": "uint256", "name": "uAmount", "type": "uint256"},
                ],
                "name": "subscribe",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            },
        ]
        
        self.proxies: list[str] = []
        self.proxy_index = 0
        self.account_proxies: Dict[str, str] = {}
        self.used_nonce: Dict[str, int] = {}
        self.nonce_locks: Dict[str, asyncio.Lock] = {} 
        self.subscribe_count = 0
        self.subscribe_amount = 0.0
        self.redeem_count = 0
        self.redeem_amount = 0.0
        self.min_delay = 0
        self.max_delay = 0

    
    def clear_terminal(self):
        os.system("cls" if os.name == "nt" else "clear")

    def log(self, message: str):
        ts = datetime.now().astimezone(wib).strftime("%x %X %Z")
        print(f"{Fore.CYAN + Style.BRIGHT}[ {ts} ]{Style.RESET_ALL} {message}", flush=True)

    def welcome(self):
        print(
            f"{Fore.GREEN + Style.BRIGHT}Asseto Finance{Fore.BLUE + Style.BRIGHT} Auto BOT V2 {Style.RESET_ALL}\n"
            f"{Fore.GREEN + Style.BRIGHT} Updated: Alternate Subscribe ↔ Redeem (Option 3){Style.RESET_ALL}"
        )

    def format_seconds(self, seconds: int) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    
    async def load_proxies(self, filename: str = "proxy.txt"):
        try:
            if not os.path.exists(filename):
                self.log(f"{Fore.RED + Style.BRIGHT}File {filename} Not Found.{Style.RESET_ALL}")
                self.proxies = []
                return

            with open(filename, "r") as f:
                self.proxies = [line.strip() for line in f.read().splitlines() if line.strip()]

            if not self.proxies:
                self.log(f"{Fore.RED + Style.BRIGHT}No Proxies Found.{Style.RESET_ALL}")
                return

            self.log(
                f"{Fore.GREEN + Style.BRIGHT}Proxies Total : {Style.RESET_ALL}{Fore.WHITE + Style.BRIGHT}{len(self.proxies)}{Style.RESET_ALL}"
            )
        except Exception as e:
            self.log(f"{Fore.RED + Style.BRIGHT}Failed To Load Proxies: {e}{Style.RESET_ALL}")
            self.proxies = []

    def check_proxy_schemes(self, proxy: str) -> str:
        schemes = ("http://", "https://", "socks4://", "socks5://")
        if any(proxy.startswith(s) for s in schemes):
            return proxy
        return f"http://{proxy}"

    def get_next_proxy_for_account(self, token: str) -> Optional[str]:
        if token not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[token] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[token]

    def rotate_proxy_for_account(self, token: str) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[token] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy

    def build_proxy_config(self, proxy: Optional[str]) -> Tuple[Optional[ProxyConnector], Optional[str], Optional[BasicAuth]]:
        if not proxy:
            return None, None, None
        proxy = proxy.strip()
        if proxy.startswith("socks"):
            connector = ProxyConnector.from_url(proxy)
            return connector, None, None
        elif proxy.startswith("http"):
            
            match = re.match(r"http://(.*?):(.*?)@(.*)", proxy)
            if match:
                username, password, host_port = match.groups()
                clean_url = f"http://{host_port}"
                auth = BasicAuth(username, password)
                return None, clean_url, auth
            else:
                return None, proxy, None
        raise Exception("Unsupported Proxy Type.")

    
    def generate_address(self, private_key: str) -> Optional[str]:
        try:
            acct = Account.from_key(private_key)
            return acct.address
        except Exception:
            return None

    def mask_account(self, address: str) -> Optional[str]:
        try:
            return address[:6] + "*" * 6 + address[-6:]
        except Exception:
            return None

    
    async def get_web3_with_check(self, address: str, use_proxy: bool, retries: int = 3, timeout: int = 60) -> Web3:
        request_kwargs: dict[str, Any] = {"timeout": timeout}
        proxy = self.get_next_proxy_for_account(address) if use_proxy else None
        if use_proxy and proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}
        for attempt in range(retries):
            try:
                
                web3 = Web3(Web3.HTTPProvider(self.RPC_URL, request_kwargs=request_kwargs))
                
                await asyncio.to_thread(web3.eth.get_block_number)
                return web3
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                raise Exception(f"Failed to Connect to RPC: {str(e)}")

    async def get_token_balance(self, address: str, contract_address: str, use_proxy: bool) -> Optional[float]:
        """
        Safely get token balance. Returns None if call fails or contract has no code.
        """
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)
            
            contract_addr = to_checksum_address(contract_address)
            wallet_addr = to_checksum_address(address)

            
            code = await asyncio.to_thread(web3.eth.get_code, contract_addr)
            if not code or code == b"":
                self.log(f"{Fore.CYAN+Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.YELLOW + Style.BRIGHT} Contract at {contract_addr} has no code (not a contract).{Style.RESET_ALL}")
                return None

            token_contract = web3.eth.contract(address=contract_addr, abi=self.CONTRACT_ABI)

            
            def _call_balance():
                return token_contract.functions.balanceOf(wallet_addr).call()

            def _call_decimals():
                return token_contract.functions.decimals().call()

            try:
                balance = await asyncio.to_thread(_call_balance)
                decimals = await asyncio.to_thread(_call_decimals)
            except Exception as e:
                
                self.log(f"{Fore.CYAN+Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} balanceOf/decimals call failed: {str(e)} {Style.RESET_ALL}")
                return None

            token_balance = balance / (10 ** decimals)
            return token_balance
        except Exception as e:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} {str(e)} {Style.RESET_ALL}")
            return None

    
    def _ensure_nonce_lock(self, address: str):
        if address not in self.nonce_locks:
            self.nonce_locks[address] = asyncio.Lock()

    async def get_pending_nonce(self, web3: Web3, address: str) -> int:
        
        return await asyncio.to_thread(web3.eth.get_transaction_count, address, "pending")

    async def send_raw_transaction_with_retries(self, private_key: str, web3: Web3, tx: dict, retries: int = 5) -> str:
        last_exc = None
        for attempt in range(retries):
            try:
                
                signed = await asyncio.to_thread(web3.eth.account.sign_transaction, tx, private_key)
                raw = signed.raw_transaction
                sent = await asyncio.to_thread(web3.eth.send_raw_transaction, raw)
                tx_hash = web3.to_hex(sent)
                return tx_hash
            except Exception as e:
                last_exc = e
                self.log(f"{Fore.CYAN + Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.YELLOW + Style.BRIGHT} [Attempt {attempt + 1}] Send TX Error: {str(e)} {Style.RESET_ALL}")
                await asyncio.sleep(min(2 ** attempt, 10))
                continue
        raise Exception(f"Transaction Hash Not Found After Maximum Retries: {last_exc}")

    async def wait_for_receipt_with_retries(self, web3: Web3, tx_hash: str, retries: int = 5, timeout: int = 300):
        for attempt in range(retries):
            try:
                
                receipt = await asyncio.to_thread(web3.eth.wait_for_transaction_receipt, tx_hash, timeout)
                return receipt
            except TransactionNotFound:
                pass
            except Exception as e:
                self.log(f"{Fore.CYAN + Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.YELLOW + Style.BRIGHT} [Attempt {attempt + 1}] Wait for Receipt Error: {str(e)} {Style.RESET_ALL}")
            await asyncio.sleep(2 ** attempt)
        raise Exception("Transaction Receipt Not Found After Maximum Retries")

    async def estimate_gas_safe(self, web3: Web3, contract_function, from_address: str) -> int:
        """Safely estimate gas with fallback"""
        try:
            estimated_gas = await asyncio.to_thread(contract_function.estimate_gas, {'from': from_address})
            return int(estimated_gas * 1.2)  
        except Exception as e:
            self.log(f"{Fore.YELLOW}Gas estimation failed, using default: {e}{Style.RESET_ALL}")
            return 200000  

    
    async def approving_token(self, private_key: str, address: str, router_address: str, asset_address: str, amount: int, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)
            token_contract = web3.eth.contract(address=to_checksum_address(asset_address), abi=self.CONTRACT_ABI)
            allowance = await asyncio.to_thread(token_contract.functions.allowance(address, router_address).call)
            if allowance >= amount:
                return True

            approve_fn = token_contract.functions.approve(router_address, amount)
            estimated_gas = await self.estimate_gas_safe(web3, approve_fn, address)
            
            
            max_priority_fee = web3.to_wei(1, "gwei")  
            max_fee = max_priority_fee * 2

            
            self._ensure_nonce_lock(address)
            async with self.nonce_locks[address]:
                
                pending_nonce = await self.get_pending_nonce(web3, address)
                self.used_nonce[address] = pending_nonce

                approve_tx = approve_fn.build_transaction(
                    {
                        "from": address,
                        "gas": estimated_gas,
                        "maxFeePerGas": int(max_fee),
                        "maxPriorityFeePerGas": int(max_priority_fee),
                        "nonce": self.used_nonce[address],
                        "chainId": web3.eth.chain_id,
                    }
                )
                tx_hash = await self.send_raw_transaction_with_retries(private_key, web3, approve_tx)
                receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)
                self.used_nonce[address] += 1
            self.log(f"{Fore.CYAN+Style.BRIGHT} Approve :{Style.RESET_ALL}{Fore.GREEN+Style.BRIGHT} Success {Style.RESET_ALL}")
            await asyncio.sleep(2)
            return True
        except Exception as e:
            raise Exception(f"Approving Token Contract Failed: {str(e)}")

    async def perform_subscribe(self, private_key: str, address: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)
            router_address = to_checksum_address(self.CASH_CONTRACT_ADDRESS)
            asset_address = to_checksum_address(self.USDT_CONTRACT_ADDRESS)
            amount_to_wei = int(self.subscribe_amount * (10 ** 6)) 

            
            await self.approving_token(private_key, address, router_address, asset_address, amount_to_wei, use_proxy)

            token_contract = web3.eth.contract(address=router_address, abi=self.CONTRACT_ABI)
            subscribe_fn = token_contract.functions.subscribe(asset_address, amount_to_wei)
            
            
            estimated_gas = await self.estimate_gas_safe(web3, subscribe_fn, to_checksum_address(address))

            max_priority_fee = web3.to_wei(1, "gwei")  
            max_fee = max_priority_fee * 2

            self._ensure_nonce_lock(address)
            async with self.nonce_locks[address]:
                pending_nonce = await self.get_pending_nonce(web3, address)
                self.used_nonce[address] = pending_nonce

                subscribe_tx = subscribe_fn.build_transaction(
                    {
                        "from": to_checksum_address(address),
                        "gas": estimated_gas,
                        "maxFeePerGas": int(max_fee),
                        "maxPriorityFeePerGas": int(max_priority_fee),
                        "nonce": self.used_nonce[address],
                        "chainId": web3.eth.chain_id,
                    }
                )

                tx_hash = await self.send_raw_transaction_with_retries(private_key, web3, subscribe_tx)
                receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)
                block_number = receipt.blockNumber
                self.used_nonce[address] += 1

            return tx_hash, block_number
        except Exception as e:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} {str(e)} {Style.RESET_ALL}")
            return None, None

    async def perform_redemption(self, private_key: str, address: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)
            router_address = to_checksum_address(self.CASH_CONTRACT_ADDRESS)
            asset_address = to_checksum_address(self.USDT_CONTRACT_ADDRESS)
            token_contract = web3.eth.contract(address=router_address, abi=self.CONTRACT_ABI)
            amount_to_wei = int(self.redeem_amount * (10 ** 18)) 

            redemption_fn = token_contract.functions.redemption(asset_address, amount_to_wei)
            
            
            estimated_gas = await self.estimate_gas_safe(web3, redemption_fn, to_checksum_address(address))

            max_priority_fee = web3.to_wei(1, "gwei")  
            max_fee = max_priority_fee * 2

            self._ensure_nonce_lock(address)
            async with self.nonce_locks[address]:
                pending_nonce = await self.get_pending_nonce(web3, address)
                self.used_nonce[address] = pending_nonce

                redemption_tx = redemption_fn.build_transaction(
                    {
                        "from": to_checksum_address(address),
                        "gas": estimated_gas,
                        "maxFeePerGas": int(max_fee),
                        "maxPriorityFeePerGas": int(max_priority_fee),
                        "nonce": self.used_nonce[address],
                        "chainId": web3.eth.chain_id,
                    }
                )

                tx_hash = await self.send_raw_transaction_with_retries(private_key, web3, redemption_tx)
                receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)
                block_number = receipt.blockNumber
                self.used_nonce[address] += 1

            return tx_hash, block_number
        except Exception as e:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Message :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} {str(e)} {Style.RESET_ALL}")
            return None, None

    
    async def print_timer(self):
        remaining = random.randint(self.min_delay, self.max_delay) if self.max_delay >= self.min_delay else self.min_delay
        for r in range(remaining, 0, -1):
            ts = datetime.now().astimezone(wib).strftime("%x %X %Z")
            print(f"{Fore.CYAN + Style.BRIGHT}[ {ts} ]{Style.RESET_ALL} {Fore.WHITE + Style.BRIGHT} | {Fore.BLUE + Style.BRIGHT}Wait For{Style.RESET_ALL} {Fore.WHITE + Style.BRIGHT} {r} {Style.RESET_ALL} {Fore.BLUE + Style.BRIGHT}Seconds For Next Tx...{Style.RESET_ALL}", end="\r", flush=True)
            await asyncio.sleep(1)
        print("") 

    def print_subscribe_question(self):
        while True:
            try:
                subscribe_count = int(input(f"{Fore.YELLOW + Style.BRIGHT}Enter Subscribe Count -> {Style.RESET_ALL}").strip())
                if subscribe_count > 0:
                    self.subscribe_count = subscribe_count
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Subscribe Count must be > 0.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

        while True:
            try:
                subscribe_amount = float(input(f"{Fore.YELLOW + Style.BRIGHT}Enter Subscribe Amount [USDT] -> {Style.RESET_ALL}").strip())
                if subscribe_amount > 0:
                    self.subscribe_amount = subscribe_amount
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}subscribe Amount must be > 0.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a float or decimal number.{Style.RESET_ALL}")

    def print_redeem_question(self):
        while True:
            try:
                redeem_count = int(input(f"{Fore.YELLOW + Style.BRIGHT}Enter Redeem Count -> {Style.RESET_ALL}").strip())
                if redeem_count > 0:
                    self.redeem_count = redeem_count
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Redeem Count must be > 0.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

        while True:
            try:
                redeem_amount = float(input(f"{Fore.YELLOW + Style.BRIGHT}Enter Redeem Amount [CASH+] -> {Style.RESET_ALL}").strip())
                if redeem_amount > 0:
                    self.redeem_amount = redeem_amount
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Redeem Amount must be > 0.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a float or decimal number.{Style.RESET_ALL}")

    def print_delay_question(self):
        while True:
            try:
                min_delay = int(input(f"{Fore.YELLOW + Style.BRIGHT}Min Delay For Each Tx -> {Style.RESET_ALL}").strip())
                if min_delay >= 0:
                    self.min_delay = min_delay
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Min Delay must be >= 0.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

        while True:
            try:
                max_delay = int(input(f"{Fore.YELLOW + Style.BRIGHT}Max Delay For Each Tx -> {Style.RESET_ALL}").strip())
                if max_delay >= self.min_delay:
                    self.max_delay = max_delay
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Max Delay must be >= Min Delay.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

    def print_question(self):
        while True:
            try:
                print(f"{Fore.GREEN + Style.BRIGHT}Select Option:{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}1. Subscribe{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}2. Redeem{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}3. Run All Features (Alternate Subscribe ↔ Redeem){Style.RESET_ALL}")
                option = int(input(f"{Fore.BLUE + Style.BRIGHT}Choose [1/2/3] -> {Style.RESET_ALL}").strip())
                if option in [1, 2, 3]:
                    option_type = ("Subscribe" if option == 1 else "Redeem" if option == 2 else "Run All Features (Alternate)")
                    print(f"{Fore.GREEN + Style.BRIGHT}{option_type} Selected.{Style.RESET_ALL}")
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Please enter either 1, 2, or 3.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number (1, 2, or 3).{Style.RESET_ALL}")

        if option == 1:
            self.print_subscribe_question()
            self.print_delay_question()
        elif option == 2:
            self.print_redeem_question()
            self.print_delay_question()
        else:
            self.print_subscribe_question()
            self.print_redeem_question()
            self.print_delay_question()

        while True:
            try:
                print(f"{Fore.WHITE + Style.BRIGHT}1. Run With Proxy{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}2. Run Without Proxy{Style.RESET_ALL}")
                proxy_choice = int(input(f"{Fore.BLUE + Style.BRIGHT}Choose [1/2] -> {Style.RESET_ALL}").strip())
                if proxy_choice in [1, 2]:
                    typ = "With" if proxy_choice == 1 else "Without"
                    print(f"{Fore.GREEN + Style.BRIGHT}Run {typ} Proxy Selected.{Style.RESET_ALL}")
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Please enter either 1 or 2.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number (1 or 2).{Style.RESET_ALL}")

        rotate_proxy = False
        if proxy_choice == 1:
            while True:
                ans = input(f"{Fore.BLUE + Style.BRIGHT}Rotate Invalid Proxy? [y/n] -> {Style.RESET_ALL}").strip().lower()
                if ans in ("y", "n"):
                    rotate_proxy = ans == "y"
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter 'y' or 'n'.{Style.RESET_ALL}")

        return option, proxy_choice, rotate_proxy

    async def check_connection(self, proxy_url: Optional[str] = None) -> Optional[bool]:
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            timeout = ClientTimeout(total=10)
            async with ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(url="https://api.ipify.org?format=json", proxy=proxy, proxy_auth=proxy_auth) as response:
                    response.raise_for_status()
                    return True
        except (ClientResponseError, Exception) as e:
            self.log(f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} Connection Not 200 OK {Style.RESET_ALL}{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}")
            return None

    async def process_check_connection(self, address: str, use_proxy: bool, rotate_proxy: bool) -> bool:
        while True:
            proxy = self.get_next_proxy_for_account(address) if use_proxy else None
            self.log(f"{Fore.CYAN+Style.BRIGHT}Proxy :{Style.RESET_ALL}{Fore.WHITE + Style.BRIGHT} {proxy} {Style.RESET_ALL}")
            is_valid = await self.check_connection(proxy)
            if not is_valid:
                if rotate_proxy:
                    _ = self.rotate_proxy_for_account(address)
                    await asyncio.sleep(1)
                    continue
                return False
            return True

    
    async def process_perform_subscribe(self, private_key: str, address: str, use_proxy: bool):
        tx_hash, block_number = await self.perform_subscribe(private_key, address, use_proxy)
        if tx_hash and block_number:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Status :{Style.RESET_ALL}{Fore.GREEN+Style.BRIGHT} Success {Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Block :{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {block_number} {Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Tx Hash :{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {tx_hash} {Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Explorer:{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {self.EXPLORER}{tx_hash} {Style.RESET_ALL}")
        else:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Status :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} Perform On-Chain Failed {Style.RESET_ALL}")

    async def process_perform_redemption(self, private_key: str, address: str, use_proxy: bool):
        tx_hash, block_number = await self.perform_redemption(private_key, address, use_proxy)
        if tx_hash and block_number:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Status :{Style.RESET_ALL}{Fore.GREEN+Style.BRIGHT} Success {Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Block :{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {block_number} {Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Tx Hash :{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {tx_hash} {Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Explorer:{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {self.EXPLORER}{tx_hash} {Style.RESET_ALL}")
        else:
            self.log(f"{Fore.CYAN+Style.BRIGHT} Status :{Style.RESET_ALL}{Fore.RED+Style.BRIGHT} Perform On-Chain Failed {Style.RESET_ALL}")

    async def process_option_1(self, private_key: str, address: str, use_proxy: bool):
        self.log(f"{Fore.CYAN+Style.BRIGHT}Subscribe:{Style.RESET_ALL}")
        for i in range(self.subscribe_count):
            self.log(f"{Fore.GREEN+Style.BRIGHT} ● {Style.RESET_ALL}{Fore.BLUE+Style.BRIGHT}Subscribe{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {i+1}/{self.subscribe_count}{Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Amount :{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {self.subscribe_amount} USDT {Style.RESET_ALL}")
            balance = await self.get_token_balance(address, self.USDT_CONTRACT_ADDRESS, use_proxy)
            if balance is None or balance < self.subscribe_amount:
                self.log(f"{Fore.RED+Style.BRIGHT} Insufficient USDT Balance{Style.RESET_ALL}")
                break
            await self.process_perform_subscribe(private_key, address, use_proxy)
            await self.print_timer()

    async def process_option_2(self, private_key: str, address: str, use_proxy: bool):
        self.log(f"{Fore.CYAN+Style.BRIGHT}Redeem :{Style.RESET_ALL}")
        for i in range(self.redeem_count):
            self.log(f"{Fore.GREEN+Style.BRIGHT} ● {Style.RESET_ALL}{Fore.BLUE+Style.BRIGHT}Redeem{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {i+1}/{self.redeem_count}{Style.RESET_ALL}")
            self.log(f"{Fore.CYAN+Style.BRIGHT} Amount :{Style.RESET_ALL}{Fore.WHITE+Style.BRIGHT} {self.redeem_amount} CASH+ {Style.RESET_ALL}")
            balance = await self.get_token_balance(address, self.CASH_CONTRACT_ADDRESS, use_proxy)
            if balance is None or balance < self.redeem_amount:
                self.log(f"{Fore.RED+Style.BRIGHT} Insufficient CASH+ Balance{Style.RESET_ALL}")
                break
            await self.process_perform_redemption(private_key, address, use_proxy)
            await self.print_timer()

    async def process_accounts(self, private_key: str, address: str, option: int, use_proxy: bool, rotate_proxy: bool):
        is_valid = await self.process_check_connection(address, use_proxy, rotate_proxy)
        if not is_valid:
            return

        try:
            web3 = await self.get_web3_with_check(address, use_proxy)
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}Web3 Connection Failed: {e}{Style.RESET_ALL}")
            return

        
        pending = await self.get_pending_nonce(web3, address)
        self.used_nonce[address] = pending
        self._ensure_nonce_lock(address)

        if option == 1:
            await self.process_option_1(private_key, address, use_proxy)
        elif option == 2:
            await self.process_option_2(private_key, address, use_proxy)
        else:
            self.log(f"{Fore.CYAN+Style.BRIGHT}Option :{Style.RESET_ALL} {Fore.BLUE+Style.BRIGHT}Run All Features (Alternate Mode){Style.RESET_ALL}")
            max_cycles = max(self.subscribe_count, self.redeem_count)
            for cycle in range(1, max_cycles + 1):
                self.log(f"{Fore.MAGENTA+Style.BRIGHT}══ Cycle {cycle}/{max_cycles} ══{Style.RESET_ALL}")
                if cycle <= self.subscribe_count:
                    self.log(f"{Fore.GREEN+Style.BRIGHT}▶ Subscribe {cycle}/{self.subscribe_count}{Style.RESET_ALL}")
                    self.log(f"{Fore.CYAN+Style.BRIGHT} Amount:{Style.RESET_ALL} {self.subscribe_amount} USDT")
                    bal = await self.get_token_balance(address, self.USDT_CONTRACT_ADDRESS, use_proxy)
                    if bal is not None and bal >= self.subscribe_amount:
                        await self.process_perform_subscribe(private_key, address, use_proxy)
                    else:
                        self.log(f"{Fore.RED+Style.BRIGHT} Insufficient USDT → Skip Subscribe{Style.RESET_ALL}")

                if cycle <= self.redeem_count:
                    if cycle <= self.subscribe_count:
                        await asyncio.sleep(3)
                    self.log(f"{Fore.YELLOW+Style.BRIGHT}▶ Redeem {cycle}/{self.redeem_count}{Style.RESET_ALL}")
                    self.log(f"{Fore.CYAN+Style.BRIGHT} Amount:{Style.RESET_ALL} {self.redeem_amount} CASH+")
                    bal = await self.get_token_balance(address, self.CASH_CONTRACT_ADDRESS, use_proxy)
                    if bal is not None and bal >= self.redeem_amount:
                        await self.process_perform_redemption(private_key, address, use_proxy)
                    else:
                        self.log(f"{Fore.RED+Style.BRIGHT} Insufficient CASH+ → Skip Redeem{Style.RESET_ALL}")

                if cycle < max_cycles:
                    await self.print_timer()

    async def main(self):
        try:
            with open("accounts.txt", "r") as file:
                accounts = [line.strip() for line in file if line.strip()]

            option, proxy_choice, rotate_proxy = self.print_question()

            while True:
                self.clear_terminal()
                self.welcome()
                self.log(f"{Fore.GREEN + Style.BRIGHT}Account's Total: {len(accounts)}{Style.RESET_ALL}")

                use_proxy = proxy_choice == 1
                if use_proxy:
                    await self.load_proxies()

                for private_key in accounts:
                    if not private_key:
                        continue
                    address = self.generate_address(private_key)
                    if not address:
                        self.log(f"{Fore.RED + Style.BRIGHT}Invalid Private Key{Style.RESET_ALL}")
                        continue
                    self.log(f"{Fore.CYAN+Style.BRIGHT}═════════════════ [{self.mask_account(address)}] ═════════════════{Style.RESET_ALL}")
                    await self.process_accounts(private_key, address, option, use_proxy, rotate_proxy)
                    await asyncio.sleep(3)
                    self.log((f"{Fore.CYAN+Style.BRIGHT}═{Style.RESET_ALL}" * 72))
                
                for s in range(24 * 60 * 60, 0, -1):
                    print(f"{Fore.CYAN+Style.BRIGHT}[ Wait {self.format_seconds(s)} ]{Style.RESET_ALL} | All accounts processed.", end="\r")
                    await asyncio.sleep(1)
        except FileNotFoundError:
            self.log(f"{Fore.RED}File 'accounts.txt' Not Found.{Style.RESET_ALL}")
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}Error: {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    try:
        bot = AssetoFinance()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print(f"\n{Fore.RED + Style.BRIGHT}[EXIT] Bot Stopped by User.{Style.RESET_ALL}")
