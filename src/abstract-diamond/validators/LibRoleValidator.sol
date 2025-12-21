// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {LibDiamond} from "src/abstract-diamond/storage/LibDiamond.sol";

library LibRoleValidator {
    error LibRoleValidator__MissingRole(address user, bytes32 role);

    function onlyRole(bytes32 _role) internal view {
        require(
            LibDiamond.hasRole(msg.sender, _role),
            LibRoleValidator__MissingRole(msg.sender, _role)
        );
    }
}
