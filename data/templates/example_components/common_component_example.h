/******************************************************************************
 * Copyright 2023 The Apollo Authors. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *****************************************************************************/
#pragma once
#include <memory>

#include "cyber/cyber.h"
#include "example_components/proto/examples.pb.h"
#include "example_lib/external_lib.h"

namespace apollo {
namespace example {

  class CommonComponentSample : public cyber::Component<example::proto::Driver, example::proto::Driver> {
    public:
    bool Init() override;
    bool Proc(const std::shared_ptr<example::proto::Driver>& msg0,
        const std::shared_ptr<example::proto::Driver>& msg1) override;
  };
  CYBER_REGISTER_COMPONENT(CommonComponentSample)

} // namespace example
} //namespace apollo
