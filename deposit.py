import argparse
from sha3 import sha3_256
import sys
from web3 import Web3, RPCProvider


abi = [{"constant":True,"inputs":[],"name":"totalPaidOut","outputs":[{"name":"","type":"uint256"}],"payable":False,"type":"function"},{"constant":False,"inputs":[{"name":"newOwner","type":"address"}],"name":"setOwner","outputs":[],"payable":False,"type":"function"},{"constant":True,"inputs":[],"name":"depositCount","outputs":[{"name":"","type":"uint256"}],"payable":False,"type":"function"},{"constant":False,"inputs":[{"name":"max","type":"uint256"}],"name":"withdraw","outputs":[],"payable":False,"type":"function"},{"constant":True,"inputs":[],"name":"paidOut","outputs":[{"name":"","type":"uint256"}],"payable":False,"type":"function"},{"constant":False,"inputs":[{"name":"addr","type":"address"},{"name":"amount","type":"uint256"}],"name":"disburse","outputs":[],"payable":False,"type":"function"},{"constant":False,"inputs":[],"name":"destroy","outputs":[],"payable":False,"type":"function"},{"constant":False,"inputs":[{"name":"newAuditor","type":"address"}],"name":"setAuditor","outputs":[],"payable":False,"type":"function"},{"constant":True,"inputs":[{"name":"hash","type":"bytes16"}],"name":"nextWithdrawal","outputs":[{"name":"when","type":"uint256"},{"name":"count","type":"uint256"},{"name":"value","type":"uint256"},{"name":"next","type":"bytes16"}],"payable":False,"type":"function"},{"constant":True,"inputs":[{"name":"addr","type":"address"}],"name":"check","outputs":[{"name":"expires","type":"uint256"},{"name":"deposit","type":"uint256"}],"payable":False,"type":"function"},{"constant":False,"inputs":[{"name":"values","type":"bytes16[]"},{"name":"deposit","type":"uint64"}],"name":"deposit","outputs":[],"payable":False,"type":"function"},{"inputs":[],"payable":False,"type":"constructor"},{"anonymous":False,"inputs":[{"indexed":False,"name":"addr","type":"address"},{"indexed":False,"name":"amount","type":"uint256"}],"name":"Claim","type":"event"}]



parser = argparse.ArgumentParser(description='Deposit ether.card guarantee funds')
parser.add_argument('--rpchost', type=str, help='JSON-RPC hostname', default='localhost')
parser.add_argument('--rpcport', type=int, help='JSON-RPC port number', default=8545)
parser.add_argument('--amount', type=int, help='Deposit, in wei, per card', default=100000000000000000)
parser.add_argument('--batchsize', type=int, help='Batch size for deposit transactions', default=100)
parser.add_argument('--gaslimit', type=int, help='Gas limit', default=2500000)
parser.add_argument('--address', type=str, help='Address of deposit contract', default='0xCD6608b1291d4307652592c29bFF7d51f1AD83d7')
parser.add_argument('--sender', type=str, help='Address of sending account', default='0x32b724f073ec346edd64b0cc67757e4f6fe42950')
parser.add_argument('addresses', metavar='FILENAME', type=argparse.FileType('r'), default=sys.stdin, help='File containing list of addresses')


def read_addresses(f):
    for address in f:
        address = address.strip()
        if not address:
            continue

        if address.lower().startswith('0x'):
            address = address[2:]

        yield address


def check_addresses(contract, addresses):
    for address in addresses:
        expires, balance = contract.call().check('0x' + address)
        if expires > 0:
            print "Skipping address %s: deposit of %.2f ether already paid" % (address, balance / 1e18)
        else:
            yield address

def make_hashes(addresses):
    return [sha3_256(address.decode('hex')).digest()[:16] for address in addresses]


def chunk(l, n):
    for i in range(0, len(l), n):
        yield l[i:i+n]


def send_deposit(contract, sender, hashes, amount, gaslimit):
    print amount
    return contract.transact({
        'gas': gaslimit,
        'from': sender,
        'value': amount * len(hashes)
    }).deposit(hashes, amount)

def main(args):
    web3 = Web3(RPCProvider(args.rpchost, args.rpcport))
    contract = web3.eth.contract(abi=abi, address=args.address)

    addresses = list(check_addresses(contract, read_addresses(args.addresses)))
    hashes = make_hashes(addresses)
    batches = chunk(hashes, args.batchsize)

    for batch in batches:
        txid = send_deposit(contract, args.sender, batch, args.amount, args.gaslimit)
        print "Posted %d deposits in transaction %s" % (len(batch), txid)


if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
