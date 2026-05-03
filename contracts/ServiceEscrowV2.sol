// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * CryptoMinds 服务担保合约 V2 — BNB + ERC-20 双模式
 *
 * 与 V1 完全兼容：token = address(0) 时走 BNB 原生路径。
 * token != address(0) 时走 ERC-20 transferFrom/transfer 路径。
 *
 * 流程：
 * 1. 买家创建订单，锁入 BNB 或 ERC-20 代币
 * 2. 卖家提交服务结果
 * 3. 买家确认收货 → 资金释放给卖家
 * 4. 卖家超时不交付 → 资金退还给买家
 * 5. 买家确认超时 → 资金自动释放给卖家
 * 6. 买家争议 → 管理员仲裁（退款或放款）
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract ServiceEscrowV2 {

    address public owner;
    uint256 public defaultTimeout;
    uint256 public sellerTimeout;
    address public token;       // address(0) = BNB, else ERC-20 token address
    uint8 public decimals;      // token decimals (18 for most)

    enum OrderStatus {
        None,
        Pending,
        Delivering,
        Delivered,
        Confirmed,
        Disputed,
        Refunded,
        Expired
    }

    struct Order {
        address buyer;
        address seller;
        string serviceId;
        uint256 amount;
        uint256 createdAt;
        uint256 deliveredAt;
        uint256 buyerTimeoutAt;
        uint256 sellerTimeoutAt;
        OrderStatus status;
        string deliverResult;
    }

    mapping(bytes32 => Order) public orders;
    bytes32[] public allOrderIds;

    uint256 public totalEscrowed;
    uint256 public totalReleased;
    uint256 public totalRefunded;
    uint256 public totalDisputed;

    event OrderCreated(bytes32 indexed orderId, address indexed buyer, address indexed seller, string serviceId, uint256 amount);
    event OrderDelivered(bytes32 indexed orderId, string deliverResult);
    event OrderConfirmed(bytes32 indexed orderId, uint256 amount);
    event OrderDisputed(bytes32 indexed orderId, address indexed buyer);
    event OrderRefunded(bytes32 indexed orderId, uint256 amount, string reason);
    event OrderExpired(bytes32 indexed orderId, uint256 amount);
    event SellerTimeoutRefund(bytes32 indexed orderId, uint256 amount);
    event TimeoutUpdated(uint256 oldBuyerTimeout, uint256 newBuyerTimeout, uint256 oldSellerTimeout, uint256 newSellerTimeout);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyBuyer(bytes32 orderId) {
        require(msg.sender == orders[orderId].buyer, "Not buyer");
        _;
    }

    modifier onlySeller(bytes32 orderId) {
        require(msg.sender == orders[orderId].seller, "Not seller");
        _;
    }

    constructor(uint256 _buyerTimeout, uint256 _sellerTimeout, address _token, uint8 _decimals) {
        owner = msg.sender;
        defaultTimeout = _buyerTimeout > 0 ? _buyerTimeout : 24 hours;
        sellerTimeout = _sellerTimeout > 0 ? _sellerTimeout : 30 minutes;
        token = _token;
        decimals = _decimals;
    }

    function createOrder(
        address seller,
        string calldata serviceId,
        uint256 buyerTimeoutSeconds,
        uint256 sellerTimeoutSeconds,
        uint256 amount
    ) external payable returns (bytes32 orderId) {
        require(seller != address(0), "Invalid seller");
        require(seller != msg.sender, "Cannot buy from self");
        require(bytes(serviceId).length > 0, "Invalid serviceId");

        orderId = keccak256(abi.encodePacked(
            msg.sender,
            seller,
            serviceId,
            block.timestamp,
            allOrderIds.length
        ));

        uint256 orderAmount;
        if (token == address(0)) {
            // BNB mode
            require(msg.value > 0, "Must deposit BNB > 0");
            orderAmount = msg.value;
        } else {
            // ERC-20 mode
            require(msg.value == 0, "No BNB for ERC-20 orders");
            require(amount > 0, "Must specify ERC-20 amount > 0");
            orderAmount = amount;
            require(IERC20(token).transferFrom(msg.sender, address(this), orderAmount), "ERC-20 transferFrom failed");
        }

        uint256 buyerTimeout = buyerTimeoutSeconds > 0 ? buyerTimeoutSeconds : defaultTimeout;
        uint256 sTimeout = sellerTimeoutSeconds > 0 ? sellerTimeoutSeconds : sellerTimeout;

        Order memory order = Order({
            buyer: msg.sender,
            seller: seller,
            serviceId: serviceId,
            amount: orderAmount,
            createdAt: block.timestamp,
            deliveredAt: 0,
            buyerTimeoutAt: block.timestamp + buyerTimeout,
            sellerTimeoutAt: block.timestamp + sTimeout,
            status: OrderStatus.Pending,
            deliverResult: ""
        });

        orders[orderId] = order;
        allOrderIds.push(orderId);
        totalEscrowed += orderAmount;

        emit OrderCreated(orderId, msg.sender, seller, serviceId, orderAmount);
    }

    function deliver(bytes32 orderId, string calldata result) external onlySeller(orderId) {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Pending || order.status == OrderStatus.Delivering,
            "Order not pending/delivering"
        );
        require(block.timestamp < order.sellerTimeoutAt, "Seller timeout exceeded");

        order.status = OrderStatus.Delivered;
        order.deliveredAt = block.timestamp;
        order.deliverResult = result;
        order.buyerTimeoutAt = block.timestamp + defaultTimeout;

        emit OrderDelivered(orderId, result);
    }

    function confirm(bytes32 orderId) external onlyBuyer(orderId) {
        Order storage order = orders[orderId];
        require(order.status == OrderStatus.Delivered, "Order not delivered");

        order.status = OrderStatus.Confirmed;
        uint256 amount = order.amount;
        order.amount = 0;
        totalReleased += amount;

        _transfer(order.seller, amount);

        emit OrderConfirmed(orderId, amount);
    }

    function dispute(bytes32 orderId) external onlyBuyer(orderId) {
        Order storage order = orders[orderId];
        require(order.status == OrderStatus.Delivered, "Order not delivered");

        order.status = OrderStatus.Disputed;
        totalDisputed += 1;

        emit OrderDisputed(orderId, msg.sender);
    }

    function claimBuyerTimeout(bytes32 orderId) external {
        Order storage order = orders[orderId];
        require(order.status == OrderStatus.Delivered, "Order not delivered");
        require(block.timestamp >= order.buyerTimeoutAt, "Buyer not timed out yet");

        order.status = OrderStatus.Expired;
        uint256 amount = order.amount;
        order.amount = 0;
        totalReleased += amount;

        _transfer(order.seller, amount);

        emit OrderExpired(orderId, amount);
    }

    function claimSellerTimeout(bytes32 orderId) external {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Pending || order.status == OrderStatus.Delivering,
            "Order not pending/delivering"
        );
        require(block.timestamp >= order.sellerTimeoutAt, "Seller not timed out yet");

        order.status = OrderStatus.Refunded;
        uint256 amount = order.amount;
        order.amount = 0;
        totalRefunded += amount;

        _transfer(order.buyer, amount);

        emit SellerTimeoutRefund(orderId, amount);
    }

    function arbitrateRefund(bytes32 orderId, string calldata reason) external onlyOwner {
        Order storage order = orders[orderId];
        require(order.status == OrderStatus.Disputed, "Order not disputed");

        order.status = OrderStatus.Refunded;
        uint256 amount = order.amount;
        order.amount = 0;
        totalRefunded += amount;

        _transfer(order.buyer, amount);

        emit OrderRefunded(orderId, amount, reason);
    }

    function arbitrateRelease(bytes32 orderId) external onlyOwner {
        Order storage order = orders[orderId];
        require(order.status == OrderStatus.Disputed, "Order not disputed");

        order.status = OrderStatus.Confirmed;
        uint256 amount = order.amount;
        order.amount = 0;
        totalReleased += amount;

        _transfer(order.seller, amount);

        emit OrderConfirmed(orderId, amount);
    }

    function _transfer(address to, uint256 amount) internal {
        if (token == address(0)) {
            (bool ok, ) = payable(to).call{value: amount}("");
            require(ok, "BNB transfer failed");
        } else {
            require(IERC20(token).transfer(to, amount), "ERC-20 transfer failed");
        }
    }

    function getOrder(bytes32 orderId) external view returns (
        address buyer,
        address seller,
        string memory serviceId,
        uint256 amount,
        uint256 createdAt,
        uint256 deliveredAt,
        uint256 buyerTimeoutAt,
        uint256 sellerTimeoutAt,
        OrderStatus status,
        string memory deliverResult
    ) {
        Order storage o = orders[orderId];
        return (o.buyer, o.seller, o.serviceId, o.amount, o.createdAt, o.deliveredAt, o.buyerTimeoutAt, o.sellerTimeoutAt, o.status, o.deliverResult);
    }

    function getOrderCount() external view returns (uint256) {
        return allOrderIds.length;
    }

    function setTimeouts(uint256 newBuyerTimeout, uint256 newSellerTimeout) external onlyOwner {
        require(newBuyerTimeout > 0 && newSellerTimeout > 0, "Timeout must > 0");
        emit TimeoutUpdated(defaultTimeout, newBuyerTimeout, sellerTimeout, newSellerTimeout);
        defaultTimeout = newBuyerTimeout;
        sellerTimeout = newSellerTimeout;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }

    receive() external payable {}
}