// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {LibDiamond} from "src/abstract-diamond/storage/LibDiamond.sol";
import {Errors} from "src/abstract-diamond/domain/Errors.sol";

contract RBACFacet {
    modifier onlyAdmin() {
        _onlyAdmin();
        _;
    }

    function _onlyAdmin() private view {
        require(
            LibDiamond.hasRole(msg.sender, LibDiamond.ADMIN),
            Errors.LibDiamond__Unauthorized(msg.sender)
        );
    }

    function grantRole(address account, bytes32 role) external onlyAdmin {
        LibDiamond.grantRole(account, role);
    }

    function revokeRole(address account, bytes32 role) external onlyAdmin {
        LibDiamond.removeRole(account, role);
    }
}
